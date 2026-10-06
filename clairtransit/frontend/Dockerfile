FROM node:24-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0"]
