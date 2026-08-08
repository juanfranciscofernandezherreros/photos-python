Feature: Complete Photos Sync API contract
  Every published endpoint must remain reachable through its declared transport and method.

  Scenario Outline: Invoke every API endpoint
    Given the disposable Photos Sync API is running
    When I invoke <method> "<path>"
    Then the endpoint contract is reachable

    Examples:
      | method    | path                              |
      | GET       | /                                 |
      | GET       | /health                           |
      | GET       | /api/auth/status                  |
      | POST      | /api/auth/setup-admin             |
      | POST      | /api/auth/login                   |
      | POST      | /api/auth/logout                  |
      | GET       | /api/auth/me                      |
      | POST      | /api/auth/change-password         |
      | GET       | /api/auth/lockouts                |
      | DELETE    | /api/auth/lockouts/{username}     |
      | GET       | /api/users                        |
      | POST      | /api/users                        |
      | DELETE    | /api/users/{user_id}              |
      | GET       | /api/pasos                        |
      | GET       | /api/pipeline/estado              |
      | POST      | /api/pipeline/ejecutar            |
      | GET       | /api/days                         |
      | GET       | /api/days/{date}/photos           |
      | GET       | /api/photos                       |
      | GET       | /api/exif                         |
      | GET       | /api/exif/{capture_id}            |
      | GET       | /api/photo                        |
      | GET       | /api/thumb                        |
      | GET       | /api/photos/download-zip          |
      | POST      | /api/photos/bulk                  |
      | POST      | /api/photos/fix-dates             |
      | GET       | /api/favourites                   |
      | POST      | /api/favourites                   |
      | GET       | /api/tags                         |
      | GET       | /api/trash                        |
      | POST      | /api/trash/restore                |
      | POST      | /api/trash/delete                 |
      | POST      | /api/trash/empty                  |
      | POST      | /api/trash/purge-old              |
      | GET       | /api/albums                       |
      | POST      | /api/albums                       |
      | GET       | /api/albums/{album_id}            |
      | PATCH     | /api/albums/{album_id}            |
      | DELETE    | /api/albums/{album_id}            |
      | POST      | /api/albums/{album_id}/photos     |
      | GET       | /api/ssh                          |
      | GET       | /api/ssh/roles                    |
      | POST      | /api/ssh                          |
      | DELETE    | /api/ssh/{alias}                  |
      | GET       | /api/webdav                       |
      | GET       | /api/webdav/letras                |
      | POST      | /api/webdav/connect               |
      | POST      | /api/webdav/disconnect/{letra}    |
      | POST      | /api/webdav/scan                  |
      | POST      | /api/webdav/download              |
      | POST      | /api/webdav/download/retry-failed |
      | GET       | /api/webdav/download-status       |
      | GET       | /api/carpetas                     |
      | POST      | /api/carpetas/origen/anadir       |
      | POST      | /api/carpetas/origen/quitar       |
      | POST      | /api/carpetas/destino             |
      | POST      | /api/carpetas/destino/quitar      |
      | GET       | /api/diag                         |
      | WEBSOCKET | /ws/log                           |
