Feature: Albums
  As a user I want to create named albums, add photos to them,
  manage covers, and browse album contents — without moving files on disk.

  Background:
    Given the API is running

  # ── CRUD ──────────────────────────────────────────────────
  Scenario: Albums list is empty initially
    When I request GET "/api/albums"
    Then the response status is 200
    And "total" equals 0

  Scenario: Create an album
    When I POST "/api/albums" with name "Vacaciones 2024"
    Then the response status is 200
    And "ok" is true
    And the album id starts with "alb_"
    And the album name is "Vacaciones 2024"
    And the album count is 0

  Scenario: Creating album with blank name is rejected
    When I POST "/api/albums" with name "   "
    Then the response status is 400

  Scenario: Created album appears in the listing
    When I POST "/api/albums" with name "Trip"
    And I request GET "/api/albums"
    Then "total" equals 1
    And the first album name is "Trip"

  Scenario: Two albums get unique IDs
    When I POST "/api/albums" with name "A"
    And I POST "/api/albums" with name "B"
    Then the two album ids are different

  Scenario: Rename an album
    Given an album "Old Name" exists
    When I PATCH the album with name "New Name"
    Then the response status is 200
    And the album name is "New Name"

  Scenario: Rename with empty string is rejected
    Given an album "Keep" exists
    When I PATCH the album with name "  "
    Then the response status is 400

  Scenario: Rename a nonexistent album returns 404
    When I PATCH "/api/albums/alb_ghost" with name "X"
    Then the response status is 404

  Scenario: Delete an album
    Given an album "Doomed" exists
    When I DELETE the album
    Then the response status is 200
    And the albums list is empty

  Scenario: Delete a nonexistent album returns 404
    When I DELETE "/api/albums/alb_nope"
    Then the response status is 404

  # ── Photos in albums ──────────────────────────────────────
  Scenario: Add photos to an album
    Given an album "My Album" exists
    And 3 photos exist at the organized path
    When I add all photos to the album
    Then the response status is 200
    And the album photo count is 3

  Scenario: Adding the same photos twice is idempotent
    Given an album "My Album" exists
    And 3 photos exist at the organized path
    When I add all photos to the album
    And I add all photos to the album
    Then the album photo count is 3

  Scenario: Remove a photo from an album
    Given an album "My Album" exists
    And 3 photos exist at the organized path
    And all photos are added to the album
    When I remove the first photo from the album
    Then the album photo count is 2

  Scenario: Adding outside paths is silently rejected
    Given an album "Safe" exists
    When I POST album photos with paths ["/etc/passwd"] and action "add"
    Then the response status is 200
    And the album photo count is 0

  Scenario: Unknown action on album photos returns 400
    Given an album "X" exists
    When I POST album photos with paths [] and action "shuffle"
    Then the response status is 400

  Scenario: Adding photos to a nonexistent album returns 404
    When I POST "/api/albums/alb_nope/photos" with paths [] and action "add"
    Then the response status is 404

  # ── Get album details ─────────────────────────────────────
  Scenario: Get album photos returns full photo shapes
    Given an album "My Album" exists
    And 3 photos exist at the organized path
    And all photos are added to the album
    When I request GET the album detail
    Then the response status is 200
    And the album has 3 photos
    And each photo has "id", "filename", "exists", "url"

  Scenario: Get a nonexistent album returns 404
    When I request GET "/api/albums/alb_nope"
    Then the response status is 404

  # ── Cover ─────────────────────────────────────────────────
  Scenario: Cover defaults to first photo
    Given an album "My Album" exists
    And 3 photos exist at the organized path
    And all photos are added to the album
    When I request GET "/api/albums"
    Then the first album cover is the first photo

  Scenario: Set a custom cover
    Given an album "My Album" exists
    And 3 photos exist at the organized path
    And all photos are added to the album
    When I PATCH the album with cover set to the third photo
    Then the response status is 200
    When I request GET "/api/albums"
    Then the first album cover is the third photo

  Scenario: Setting cover to a photo not in album is rejected
    Given an album "My Album" exists
    And 3 photos exist at the organized path
    And only the first photo is added to the album
    When I PATCH the album with cover set to the second photo
    Then the response status is 400

  Scenario: Removing the cover photo clears it
    Given an album "My Album" exists
    And 3 photos exist at the organized path
    And all photos are added to the album
    And the cover is set to the first photo
    When I remove the first photo from the album
    Then the album cover is not the first photo

  # ── Cross-album ───────────────────────────────────────────
  Scenario: A photo can belong to multiple albums
    Given an album "A1" exists
    And an album "A2" exists
    And 1 photo exists at the organized path
    When I add all photos to album "A1"
    And I add all photos to album "A2"
    Then album "A1" has 1 photo
    And album "A2" has 1 photo

  Scenario: Deleting an album does not delete files on disk
    Given an album "Temp" exists
    And 3 photos exist at the organized path
    And all photos are added to the album
    When I DELETE the album
    Then all original photo files still exist on disk
