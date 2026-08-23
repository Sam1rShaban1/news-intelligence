# ---- Build stage ----
FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN npm install -g pnpm@10
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# ---- Runtime stage ----
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Template is rendered by the nginx image's entrypoint (envsubst), which only
# substitutes *environment* variables, so nginx vars like $upstream/$host are
# left intact. API_KEY is injected here from the frontend service env.
COPY templates /etc/nginx/templates
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
