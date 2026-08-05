package com.photosync.acceptance;

import io.cucumber.java.AfterAll;
import io.cucumber.java.Before;
import io.cucumber.java.BeforeAll;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;
import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CompletionStage;
import net.serenitybdd.core.Serenity;
import org.junit.jupiter.api.Assertions;

public class ApiSteps {
    private static Process api;
    private static URI baseUri;
    private static Path sandbox;
    private static CookieManager cookies;
    private static HttpClient client;
    private static HttpResponse<String> response;

    @BeforeAll
    public static void startApi() throws Exception {
        sandbox = Files.createTempDirectory("photos-sync-serenity-");
        int port;
        try (ServerSocket socket = new ServerSocket(0)) { port = socket.getLocalPort(); }
        baseUri = URI.create("http://127.0.0.1:" + port);
        Path repository = Path.of(System.getProperty("user.dir")).toAbsolutePath().getParent();
        String python = System.getenv().getOrDefault("SERENITY_PYTHON", "python");
        ProcessBuilder builder = new ProcessBuilder(
            python, "-m", "photos_sync", "--host", "127.0.0.1", "--port", String.valueOf(port));
        builder.directory(sandbox.toFile());
        builder.redirectErrorStream(true);
        builder.redirectOutput(sandbox.resolve("api.log").toFile());
        Map<String, String> env = builder.environment();
        env.put("PYTHONPATH", repository.toString());
        env.put("DATABASE_URL", "sqlite:///" + sandbox.resolve("serenity.db").toString().replace('\\', '/'));
        env.put("SECRET_KEY", "serenity-only-secret-key-123456789012345");
        env.put("TESTING", "1");
        env.put("PHOTOS_DIR", sandbox.resolve("photos").toString());
        Files.createDirectories(sandbox.resolve("photos"));
        api = builder.start();

        cookies = new CookieManager(null, CookiePolicy.ACCEPT_ALL);
        client = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
            .cookieHandler(cookies).connectTimeout(Duration.ofSeconds(3)).build();
        for (int attempt = 0; attempt < 60; attempt++) {
            if (!api.isAlive()) throw new IllegalStateException("API stopped:\n" + Files.readString(sandbox.resolve("api.log")));
            try {
                if (send("GET", "/health", "").statusCode() < 500) break;
            } catch (Exception ignored) { Thread.sleep(250); }
        }
        HttpResponse<String> setup = send("POST", "/api/auth/setup-admin",
            "{\"username\":\"serenity-admin\",\"password\":\"Serenity-test-123!\"}");
        Assertions.assertTrue(setup.statusCode() == 200 || setup.statusCode() == 400, setup.body());
    }

    @AfterAll
    public static void stopApi() {
        if (api != null) { api.destroy(); try { api.waitFor(); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } }
    }

    @Before
    public void authenticate() throws Exception {
        cookies.getCookieStore().removeAll();
        response = send("POST", "/api/auth/login",
            "{\"username\":\"serenity-admin\",\"password\":\"Serenity-test-123!\"}");
        Assertions.assertEquals(200, response.statusCode(), response.body());
    }

    @Given("the disposable Photos Sync API is running")
    public void apiIsRunning() { Assertions.assertTrue(api.isAlive()); }

    @When("I invoke {word} {string}")
    public void invoke(String method, String route) throws Exception {
        if (method.equals("WEBSOCKET")) {
            URI ws = URI.create(baseUri.toString().replace("http://", "ws://") + route);
            record("WebSocket request", "GET " + ws + "\nUpgrade: websocket\nCookie: [REDACTED]");
            String cookie = cookies.getCookieStore().getCookies().stream()
                .map(HttpCookie::toString).reduce((a, b) -> a + "; " + b).orElse("");
            WebSocket socket = client.newWebSocketBuilder().header("Cookie", cookie)
                .connectTimeout(Duration.ofSeconds(3)).buildAsync(ws, new WebSocket.Listener() {
                    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
                        webSocket.request(1); return null;
                    }
                }).join();
            record("WebSocket response", "101 Switching Protocols\nConnection established successfully");
            socket.sendClose(WebSocket.NORMAL_CLOSURE, "contract checked").join();
            response = null;
            return;
        }
        String actualRoute = materialize(route);
        String requestBody = bodyFor(method, route);
        record("HTTP request", formatRequest(method, actualRoute, requestBody));
        response = send(method, actualRoute, requestBody);
        record("HTTP response", formatResponse(response));
    }

    @Then("the endpoint contract is reachable")
    public void contractReachable() {
        if (response == null) return;
        Assertions.assertNotEquals(405, response.statusCode(), "Wrong HTTP method");
        Assertions.assertTrue(response.statusCode() < 500,
            () -> "Server error " + response.statusCode() + ": " + response.body());
    }

    private static HttpResponse<String> send(String method, String route, String body) throws IOException, InterruptedException {
        HttpRequest.BodyPublisher publisher = body.isEmpty()
            ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(body);
        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve(route)).timeout(Duration.ofSeconds(15))
            .header("Content-Type", "application/json").method(method, publisher).build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    private static String formatRequest(String method, String route, String body) {
        return method + " " + baseUri.resolve(route) + "\n"
            + "Content-Type: application/json\n\n"
            + (body.isEmpty() ? "<empty body>" : redactSecrets(body));
    }

    private static String formatResponse(HttpResponse<String> result) {
        String contentType = result.headers().firstValue("content-type").orElse("<not provided>");
        String responseBody = result.body() == null || result.body().isEmpty()
            ? "<empty body>" : result.body();
        return "HTTP " + result.statusCode() + "\nContent-Type: " + contentType + "\n\n" + responseBody;
    }

    private static String redactSecrets(String body) {
        return body.replaceAll(
            "(?i)(\\\"(?:password|current_password|new_password)\\\"\\s*:\\s*\\\")[^\\\"]*(\\\")",
            "$1***$2"
        );
    }

    private static void record(String title, String contents) {
        Serenity.recordReportData().withTitle(title).andContents(contents);
    }

    private static String materialize(String route) {
        String value = route.replace("{user_id}", "missing-user").replace("{album_id}", "missing-album")
            .replace("{date}", "2024-01-01").replace("{letra}", "Z%3A")
            .replace("{alias}", "missing-ssh").replace("{username}", "nobody");
        if (route.equals("/api/photo") || route.equals("/api/thumb")) value += "?path=" + sandbox.resolve("missing.jpg").toUri();
        return value;
    }

    private static String bodyFor(String method, String route) {
        if (method.equals("GET") || method.equals("DELETE")) return "";
        return switch (route) {
            case "/api/auth/setup-admin" -> json("username", "other-admin", "password", "Other-test-123!");
            case "/api/auth/login" -> json("username", "serenity-admin", "password", "Serenity-test-123!");
            case "/api/auth/change-password" -> json("current_password", "wrong", "new_password", "New-test-123!");
            case "/api/users" -> json("username", "bdd-user", "password", "BDD-test-123!", "role", "user");
            case "/api/albums" -> json("name", "Serenity album");
            case "/api/albums/{album_id}" -> json("name", "Renamed");
            case "/api/albums/{album_id}/photos" -> "{\"paths\":[],\"action\":\"add\"}";
            case "/api/photos/bulk" -> "{\"paths\":[],\"action\":\"favourite\"}";
            case "/api/favourites" -> "{\"path\":\"missing.jpg\",\"favourite\":true}";
            case "/api/trash/restore", "/api/trash/delete" -> "{\"ids\":[]}";
            case "/api/pipeline/ejecutar" -> "{\"pasos\":[]}";
            case "/api/ssh" -> "{\"alias\":\"bdd-ssh\",\"host\":\"127.0.0.1\",\"puerto\":22,\"usuario\":\"bdd\",\"ruta_remota\":\"/photos\"}";
            case "/api/webdav/connect" -> "{\"letra\":\"Z:\",\"ip\":\"127.0.0.1\",\"puerto\":\"1\",\"alias\":\"bdd\"}";
            case "/api/webdav/scan", "/api/webdav/download" -> "{\"ip\":\"127.0.0.1\",\"port\":\"1\"}";
            case "/api/carpetas/origen/anadir", "/api/carpetas/origen/quitar" -> json("carpeta", sandbox.resolve("photos").toString());
            case "/api/carpetas/destino" -> "{\"tipo\":\"local\",\"ruta\":\"" + escape(sandbox.resolve("photos").toString()) + "\"}";
            default -> "{}";
        };
    }

    private static String json(String... pairs) {
        StringBuilder result = new StringBuilder("{");
        for (int i = 0; i < pairs.length; i += 2) {
            if (i > 0) result.append(',');
            result.append('"').append(escape(pairs[i])).append("\":\"").append(escape(pairs[i + 1])).append('"');
        }
        return result.append('}').toString();
    }

    private static String escape(String value) { return value.replace("\\", "\\\\").replace("\"", "\\\""); }
}
