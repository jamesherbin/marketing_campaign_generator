# Marketing Campaign Dashboard - Production Dockerfile
# Multi-stage build for optimized Next.js standalone output

# =============================================================================
# Stage 1: Dependencies
# =============================================================================
FROM oven/bun:1.3.14-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copy Bun package files
COPY package.json bun.lock ./

# Install ALL dependencies (including devDependencies like typescript, tailwind)
RUN bun install --frozen-lockfile

# =============================================================================
# Stage 2: Builder
# =============================================================================
FROM oven/bun:1.3.14-alpine AS builder
WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build arguments for environment variables (needed at build time for NEXT_PUBLIC_*)
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_FRONTEND_URL
ARG NEXT_PUBLIC_FIREBASE_API_KEY
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID
ARG NEXT_PUBLIC_FIREBASE_APP_ID
ARG NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_FRONTEND_URL=${NEXT_PUBLIC_FRONTEND_URL}
ENV NEXT_PUBLIC_FIREBASE_API_KEY=${NEXT_PUBLIC_FIREBASE_API_KEY}
ENV NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=${NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN}
ENV NEXT_PUBLIC_FIREBASE_PROJECT_ID=${NEXT_PUBLIC_FIREBASE_PROJECT_ID}
ENV NEXT_PUBLIC_FIREBASE_APP_ID=${NEXT_PUBLIC_FIREBASE_APP_ID}
ENV NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=${NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID}

# Build the application
ENV NEXT_TELEMETRY_DISABLED=1
RUN test -n "$NEXT_PUBLIC_FIREBASE_API_KEY" \
    && test -n "$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN" \
    && test -n "$NEXT_PUBLIC_FIREBASE_PROJECT_ID" \
    && test -n "$NEXT_PUBLIC_FIREBASE_APP_ID" \
    && test -n "$NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID"
RUN bun run build

# =============================================================================
# Stage 3: Runner (Production)
# =============================================================================
FROM node:20-alpine AS runner
WORKDIR /app

# Local Compose builds set this to the developer UID so a mode-0600 host ADC
# file remains private and readable. Production retains the non-root nextjs UID.
ARG APP_UID=1001

# Set production environment only in the final runtime stage
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy necessary files from builder
COPY --from=builder /app/public ./public

# Set correct permissions for prerender cache
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Copy standalone build output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Compose may run this image with the host UID; keep Next's writable cache
# directory owned by that UID. The production default remains nextjs (1001).
RUN chown -R "${APP_UID}:nodejs" .next

USER nextjs

# Cloud Run uses PORT environment variable
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start the server
CMD ["node", "server.js"]
