# Tablero de Talentia Insights: se compila con Node y lo sirve nginx, que
# tambien reenvia /api a la API. Asi el navegador ve una sola direccion.
FROM node:24-alpine AS compilar
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# La API se llama en la misma direccion del tablero (nginx.conf)
ENV VITE_API_URL=/api
RUN npm run build

FROM nginx:1.28-alpine
# openssl: genera un certificado autofirmado si la empresa no pone el suyo
RUN apk add --no-cache openssl && rm -f /etc/nginx/conf.d/default.conf
COPY nginx/comun.conf nginx/http.conf nginx/https.conf /etc/nginx/talentia/
# Al arrancar elige HTTP o HTTPS segun WEB_HTTPS y WEB_ESCUCHA
COPY nginx/talentia-https.sh /docker-entrypoint.d/40-talentia-https.sh
# sin CR por si el repositorio se clono en Windows con finales de linea CRLF
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-talentia-https.sh && chmod +x /docker-entrypoint.d/40-talentia-https.sh
COPY --from=compilar /web/dist /usr/share/nginx/html
EXPOSE 80 443
