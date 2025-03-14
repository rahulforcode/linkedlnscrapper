API Endpoints

POST /login-linkedin🔹 Logs into LinkedIn and stores cookies.🔹 Requires Authorization header with Bearer token.

Example Request:

POST /login-linkedin HTTP/1.1
Host: localhost:8080
Authorization: Bearer MY_SUPER_SECRET_TOKEN

GET /connections?page=x&size=y🔹 Retrieves paginated list of LinkedIn connections.🔹 Requires Authorization header with Bearer token.

Example Request:

GET /connections?page=1&size=10 HTTP/1.1
Host: localhost:8080
Authorization: Bearer MY_SUPER_SECRET_TOKEN
