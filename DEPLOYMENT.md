# Aetherdesk Call Center - Deployment Guide

## Overview

This guide covers the deployment of the Aetherdesk Call Center application, which has been modernized with Supabase for authentication, real-time features, and data management.

## Architecture

- **Frontend**: React + Vite (agent-ui)
- **Backend**: Supabase (Auth, Database, Realtime)
- **Real-time**: Supabase Realtime (replaces legacy WebSocket)
- **Authentication**: Supabase Auth (JWT-based)

## Prerequisites

- Node.js 18+ and npm/yarn
- A Supabase account and project ([supabase.com](https://supabase.com))
- Git

## 1. Supabase Setup

### Create a Supabase Project

1. Go to [app.supabase.com](https://app.supabase.com)
2. Create a new project
3. Note your project URL and anon key from Settings → API

### Database Schema

Run the SQL from `agent-ui/SUPABASE_SETUP.md` in your Supabase SQL editor:

```sql
-- See agent-ui/SUPABASE_SETUP.md for complete schema
```

This creates:
- `agents` table with RLS policies
- `calls` table with RLS policies  
- `chat_messages` table with RLS policies
- Real-time subscriptions setup

### Enable Realtime

1. Go to Database → Replication in Supabase dashboard
2. Enable realtime for: `agents`, `calls`, `chat_messages`

## 2. Environment Configuration

### Frontend (agent-ui)

Copy `.env.example` to `.env`:

```bash
cd agent-ui
cp .env.example .env
```

Update with your Supabase credentials:

```env
VITE_SUPABASE_URL=https://your-project-id.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key-here
```

## 3. Installation

### Install Dependencies

```bash
cd agent-ui
npm install
```

Key dependencies:
- `@supabase/supabase-js` - Supabase client
- `zod` - Runtime validation
- `react-router-dom` - Routing
- `recharts` - Analytics charts

### Development

```bash
npm run dev
```

App runs at http://localhost:5173

### Production Build

```bash
npm run build
```

Optimized build created in `dist/`

## 4. Production Deployment

### Option A: Vercel

1. Connect your GitHub repo to Vercel
2. Set environment variables in Vercel dashboard
3. Deploy from main branch

### Option B: Netlify

1. Connect repo to Netlify
2. Build command: `npm run build`
3. Publish directory: `dist`
4. Set environment variables

### Option C: Self-Hosted (Nginx)

```bash
# Build the app
npm run build

# Copy dist to web server
scp -r dist/* user@server:/var/www/call-center/
```

Nginx config:
```nginx
server {
  listen 80;
  server_name your-domain.com;
  root /var/www/call-center;
  
  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

## 5. Security Checklist

- [ ] Environment variables are not committed to Git
- [ ] RLS policies are enabled on all tables
- [ ] HTTPS is enforced in production
- [ ] Supabase anon key is used (NOT service role key)
- [ ] Email verification is enabled for auth
- [ ] Rate limiting is configured in Supabase
- [ ] CORS is properly configured

## 6. Post-Deployment

### Verify Authentication

1. Register a new agent account
2. Check email verification works
3. Test login/logout flow

### Verify Real-time

1. Open app in two browser windows
2. Make changes in one window
3. Verify updates appear in real-time in the other

### Monitor Performance

- Check Supabase Dashboard → Logs
- Monitor Database → Performance
- Review Auth → Users for active sessions

## 7. Troubleshooting

### Issue: "Invalid API key"

- Verify `VITE_SUPABASE_ANON_KEY` is correct
- Check key hasn't been revoked in Supabase dashboard

### Issue: RLS policy errors

- Ensure user is authenticated
- Check RLS policies allow the operation
- Verify JWT token is valid

### Issue: Real-time not working

- Check Realtime is enabled for tables
- Verify WebSocket connection in browser DevTools
- Check Supabase Realtime quotas

## 8. Maintenance

### Database Backups

- Supabase automatically backs up daily
- Manual backups: Database → Backups

### Monitoring

- Set up Supabase webhooks for alerts
- Monitor error rates in Supabase Logs
- Track usage in Supabase Usage dashboard

### Updates

```bash
# Update dependencies
npm update

# Security patches
npm audit fix
```

## Support

For issues or questions:
- Check `agent-ui/SUPABASE_SETUP.md` for schema details
- Review Supabase docs: https://supabase.com/docs
- Open GitHub issue for bug reports
