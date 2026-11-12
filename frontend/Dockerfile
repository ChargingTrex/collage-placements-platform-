FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
# --host binds outside the container; the API proxy target comes from the
# compose environment so the browser still talks to a single origin.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
