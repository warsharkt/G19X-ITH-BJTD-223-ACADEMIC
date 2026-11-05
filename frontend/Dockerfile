# Tablero de Talentia Insights: se compila con Node y lo sirve nginx, que
# tambien reenvia /api a la API. Asi el navegador ve una sola direccion.
# Fijada por digest: la etiqueta puede cambiar de contenido sin avisar. Dependabot
# (.github/dependabot.yml) propone las actualizaciones.
FROM node:26-alpine@sha256:c6ad9e9c1d80f6eb607c26b4b0a132ff7a2344fad1c78ea3baa2a7d4c8de6d94 AS compilar
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# La API se llama en la misma direccion del tablero (nginx.conf)
ENV VITE_API_URL=/api
RUN npm run build

FROM nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236
# openssl: genera un certificado autofirmado si la empresa no pone el suyo
RUN apk add --no-cache openssl && rm -f /etc/nginx/conf.d/default.conf
COPY nginx/comun.conf nginx/http.conf nginx/https.conf nginx/limites.conf nginx/proxy-api.conf /etc/nginx/talentia/
# Al arrancar elige HTTP o HTTPS segun WEB_HTTPS y WEB_ESCUCHA
COPY nginx/talentia-https.sh /docker-entrypoint.d/40-talentia-https.sh
# sin CR por si el repositorio se clono en Windows con finales de linea CRLF
RUN sed -i 's/\r$//' /docker-entrypoint.d/40-talentia-https.sh && chmod +x /docker-entrypoint.d/40-talentia-https.sh
COPY --from=compilar /web/dist /usr/share/nginx/html
EXPOSE 80 443
