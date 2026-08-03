Feature: Favourites
  As a user I want to mark photos as favourites and manage them in bulk.

  Background:
    Given the API is running
    And a destination folder exists with organized photos

  Scenario: Favourites list is empty initially
    When I request GET "/api/favourites"
    Then the response status is 200
    And "favourites" is an empty list

  Scenario: Toggle a photo as favourite
    Given a photo exists at the organized path
    When I POST "/api/favourites" with path and favourite true
    Then the response status is 200
    And "ok" is true
    When I request GET "/api/favourites"
    Then "favourites" contains the photo path

  Scenario: Unfavourite a photo
    Given a photo exists at the organized path
    When I POST "/api/favourites" with path and favourite true
    And I POST "/api/favourites" with path and favourite false
    Then the response status is 200
    When I request GET "/api/favourites"
    Then "favourites" does not contain the photo path

  Scenario: Bulk favourite multiple photos
    Given 3 photos exist at the organized path
    When I POST "/api/photos/bulk" with all paths and action "favourite"
    Then the response status is 200
    And "affected" equals 3

  Scenario: Bulk unfavourite
    Given 3 photos exist at the organized path
    When I POST "/api/photos/bulk" with all paths and action "favourite"
    And I POST "/api/photos/bulk" with 1 path and action "unfavourite"
    Then "affected" equals 1

  Scenario: Bulk delete moves files to trash
    Given 3 photos exist at the organized path
    When I POST "/api/photos/bulk" with 2 paths and action "delete"
    Then the response status is 200
    And "moved" equals 2
    And the original files no longer exist
    And a .trash folder contains 2 files

  Scenario: Bulk rejects paths outside allowed bases
    When I POST "/api/photos/bulk" with paths ["/etc/passwd"] and action "favourite"
    Then the response status is 403

  Scenario: Bulk rejects unknown action
    Given 3 photos exist at the organized path
    When I POST "/api/photos/bulk" with all paths and action "explode"
    Then the response status is 400
