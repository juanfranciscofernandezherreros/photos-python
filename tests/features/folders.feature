Feature: Folders configuration
  As a user I want to configure source folders and a destination for organized photos.

  Background:
    Given the API is running

  Scenario: Get initial folders config
    When I request GET "/api/carpetas"
    Then the response status is 200
    And the JSON has key "origen"
    And the JSON has key "destino"

  Scenario: Add a source folder
    When I POST "/api/carpetas/origen/anadir" with carpeta "/mnt/DCIM"
    Then the response status is 200
    And "origen" contains "/mnt/DCIM"

  Scenario: Remove a source folder
    When I POST "/api/carpetas/origen/anadir" with carpeta "/mnt/DCIM"
    And I POST "/api/carpetas/origen/quitar" with carpeta "/mnt/DCIM"
    Then the response status is 200

  Scenario: Set a local destination
    When I POST "/api/carpetas/destino" with tipo "local" and ruta "/tmp/photos"
    Then the response status is 200

  Scenario: Set an SSH destination
    Given an SSH server "backup" exists with role "destino"
    When I POST "/api/carpetas/destino" with tipo "ssh" and alias "backup"
    Then the response status is 200

  Scenario: Remove the destination
    When I POST "/api/carpetas/destino" with tipo "local" and ruta "/tmp/photos"
    And I POST "/api/carpetas/destino/quitar"
    Then the response status is 200

  # ── Pipeline ──────────────────────────────────────────────
  Scenario: Get pipeline steps
    When I request GET "/api/pasos"
    Then the response status is 200
    And the response is a list of steps with "id" and "nombre"

  Scenario: Get pipeline status
    When I request GET "/api/pipeline/estado"
    Then the response status is 200
    And the JSON has key "corriendo"
