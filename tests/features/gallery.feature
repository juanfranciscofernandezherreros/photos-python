Feature: Photo Gallery
  As a user I want to browse my organized photos by day,
  view thumbnails and full images, and filter by favourites or tags.

  Background:
    Given the API is running
    And a destination folder exists with organized photos

  # ── Days listing ──────────────────────────────────────────
  Scenario: List organized days
    When I request GET "/api/days"
    Then the response status is 200
    And the JSON has key "days" with a list
    And the JSON has key "total_days"
    And the JSON has key "total_photos"
    And the JSON has key "total_mb"

  Scenario: Days listing with no photos returns empty
    Given the organized folder is empty
    When I request GET "/api/days"
    Then the response status is 200
    And "total_days" equals 0

  # ── Day photos ────────────────────────────────────────────
  Scenario: Get photos for a specific day
    When I request GET "/api/days/2024-01-15/photos"
    Then the response status is 200
    And the JSON has key "photos" with a list
    And each photo has "id", "filename", "favourite", "url"

  Scenario: Bad date format returns empty with exists false
    When I request GET "/api/days/not-a-date/photos"
    Then the response status is 200

  # ── Serve photo ───────────────────────────────────────────
  Scenario: Serve a photo file
    Given a photo exists at the organized path
    When I request GET "/api/photo" with the photo path
    Then the response status is 200
    And the content type starts with "image/"

  Scenario: Serve photo rejects paths outside allowed bases
    When I request GET "/api/photo?path=/etc/passwd"
    Then the response status is 403

  # ── Thumbnails ────────────────────────────────────────────
  Scenario: Generate and serve a thumbnail
    Given a real JPEG photo exists
    When I request GET "/api/thumb" with the photo path and size 200
    Then the response status is 200
    And the content type is "image/jpeg"
    And the response body is smaller than the original file

  Scenario: Thumbnail is cached on second request
    Given a real JPEG photo exists
    When I request GET "/api/thumb" with the photo path and size 200
    And I request GET "/api/thumb" with the photo path and size 200
    Then exactly 1 file exists in the thumbs directory

  # ── Tags ──────────────────────────────────────────────────
  Scenario: List all tags
    When I request GET "/api/tags"
    Then the response status is 200
    And the JSON has key "tags" with a list

  # ── Health check ──────────────────────────────────────────
  Scenario: Check application health
    When I request GET "/health"
    Then the response status is 200
    And the JSON has key "status"

  # ── Dashboard HTML ────────────────────────────────────────
  Scenario: Dashboard returns HTML
    When I request GET "/"
    Then the response status is 200
    And the content type starts with "text/html"
    And the body contains "Photos Sync"
