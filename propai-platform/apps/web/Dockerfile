FROM node:20-alpine

# Set Monorepo Root
WORKDIR /app

# Install pnpm correctly
RUN npm i -g pnpm

# Copy workspace code
COPY . .

# Install dependencies across all workspaces
RUN pnpm install --no-frozen-lockfile

# Build next.js app specifically
RUN pnpm --filter @propai/web build

# Next.js Prod environment
ENV NODE_ENV=production
ENV PORT=3000
EXPOSE 3000

# Start Prod server
CMD ["pnpm", "--filter", "@propai/web", "start"]
