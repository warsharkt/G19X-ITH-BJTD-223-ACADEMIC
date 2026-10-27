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
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=compilar /web/dist /usr/share/nginx/html
EXPOSE 80
