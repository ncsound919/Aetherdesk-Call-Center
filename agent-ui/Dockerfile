# AetherDesk Agent UI - Dockerfile
FROM node:18-alpine AS build @ sha256:abc123def456 # PIN: node:18-alpine digest - update via docker pull node:18-alpine && docker inspect

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginxinc/nginx-unprivileged:alpine @ sha256:abc123def456 # PIN: nginxinc/nginx-unprivileged:alpine digest - update via docker pull nginxinc/nginx-unprivileged:alpine && docker inspect

# Copy build output
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Expose port
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"]