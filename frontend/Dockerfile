# Build from the repository root: docker build -f frontend/Dockerfile .
ARG NODE_IMAGE=node:22-bookworm-slim
ARG NGINX_IMAGE=nginx:stable-alpine

FROM ${NODE_IMAGE} AS build
WORKDIR /workspace/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
COPY contracts/ /workspace/contracts/

# An empty base URL makes the existing typed client use window.location.origin.
# These are public compile-time settings, not runtime credentials.
ENV VITE_API_MODE=real
ENV VITE_API_BASE_URL=""
RUN npm run typecheck && npm run build

FROM build AS verification
# Existing UI unit tests exercise mock mode. Production output above stays real;
# its Nginx/API behavior is checked separately by the Docker integration suite.
RUN VITE_API_MODE=mock npm test && npm run lint

FROM ${NGINX_IMAGE} AS runtime
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/frontend/dist/ /usr/share/nginx/html/
RUN nginx -t

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ready || exit 1
