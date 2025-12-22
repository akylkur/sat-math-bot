# SAT Math Кыргызча - Complete Setup & Implementation Guide

A full-stack Kyrgyz math question bank + practice platform built with Next.js 15, React 18, TypeScript, TailwindCSS, and Supabase.

## MVP Scope Delivered

✓ 4 Core Pages: Landing, Question Bank, Practice Mode, Dashboard
✓ Import Feature: Admin page + API endpoint for bulk JSON import
✓ Analytics: User tracking, DAU, accuracy metrics, retention
✓ Authentication: Email + Google OAuth + Guest mode
✓ Database: 4 tables with RLS (questions, user_profiles, attempts, events)
✓ Responsive Design: Dark mode, Kyrgyz UI text, keyboard shortcuts

---

## Quick Start (15 minutes)

### 1. Create Next.js Project

```bash
npx create-next-app@latest kyrgyz-math-bank \
  --typescript --tailwind --app --no-src-dir --import-alias '@/*'
cd kyrgyz-math-bank
```

### 2. Install Dependencies

```bash
npm install @supabase/ssr @supabase/supabase-js recharts
npm install -D @types/node @types/react @types/react-dom
```

### 3. Create `.env.local`

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
ADMIN_SECRET=your-secret-key-for-import
```

Get these from: Supabase Dashboard > Project Settings > API

### 4. Run Database Migrations

Copy each SQL block below and paste into Supabase > SQL Editor > New Query:

**Migration 1: Questions Table**
```sql
CREATE TABLE IF NOT EXISTS questions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id text UNIQUE,
  lang text DEFAULT 'ky' NOT NULL,
  topic text NOT NULL,
  difficulty text NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
  type text NOT NULL CHECK (type IN ('mcq', 'grid', 'open')),
  prompt text NOT NULL,
  choices jsonb,
  correct_answer text NOT NULL,
  explanation text,
  image_url text,
  latex text,
  tags text[],
  created_at timestamptz DEFAULT now() NOT NULL
);

ALTER TABLE questions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Questions are viewable by everyone" ON questions FOR SELECT USING (true);
CREATE INDEX idx_questions_topic ON questions(topic);
CREATE INDEX idx_questions_difficulty ON questions(difficulty);
```

**Migration 2: User Profiles**
```sql
CREATE TABLE IF NOT EXISTS user_profiles (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name text,
  created_at timestamptz DEFAULT now() NOT NULL,
  last_active_at timestamptz DEFAULT now() NOT NULL
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own profile"
  ON user_profiles FOR SELECT TO authenticated
  USING (auth.uid() = user_id);
```

**Migration 3: Attempts**
```sql
CREATE TABLE IF NOT EXISTS attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  guest_id text,
  question_id uuid REFERENCES questions(id) ON DELETE CASCADE NOT NULL,
  selected_answer text,
  is_correct boolean NOT NULL DEFAULT false,
  time_spent_sec integer DEFAULT 0 NOT NULL,
  created_at timestamptz DEFAULT now() NOT NULL,
  CONSTRAINT user_or_guest CHECK (
    (user_id IS NOT NULL AND guest_id IS NULL) OR
    (user_id IS NULL AND guest_id IS NOT NULL)
  )
);

ALTER TABLE attempts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can insert own attempts"
  ON attempts FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Authenticated users can read own attempts"
  ON attempts FOR SELECT TO authenticated
  USING (auth.uid() = user_id);
```

**Migration 4: Events**
```sql
CREATE TABLE IF NOT EXISTS events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  guest_id text,
  event_type text NOT NULL,
  metadata jsonb,
  created_at timestamptz DEFAULT now() NOT NULL
);

ALTER TABLE events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can insert own events"
  ON events FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id OR user_id IS NULL);
```

### 5. Run Development Server

```bash
npm run dev
```

Visit: http://localhost:3000

---

## File Structure & Code

All files should be created in the following structure. File locations are absolute paths from project root.

### Configuration Files

**package.json**
- Dependencies: Next.js 15, React 18, @supabase/ssr, recharts
- Scripts: dev, build, start, lint

**tsconfig.json**
- Strict mode enabled
- Path alias: @/* → ./

**tailwind.config.ts**
- Dark mode: class
- Font: System stack

**next.config.js**
- Image optimization enabled
- Remote patterns for images

**.env.local** (Create manually)
```
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
ADMIN_SECRET=your-secret
```

### Core Application Files

**app/layout.tsx**
- Root HTML structure
- Global fonts and metadata
- Dark mode enabled

**app/globals.css**
- TailwindCSS directives
- Custom animations (fadeIn)
- CSS variables for colors

**components/Header.tsx** (Client)
- Navigation bar with logo
- Auth state detection
- Sign In/Up buttons or Sign Out
- Links to main pages

**lib/supabase/client.ts** (Client)
- Browser Supabase client initialization
- Uses NEXT_PUBLIC_SUPABASE_URL and ANON_KEY

**lib/supabase/server.ts** (Server)
- Server-side Supabase client
- Handles cookies
- Used in API routes and server components

**lib/supabase/database.types.ts**
- TypeScript types for all tables
- Generated from Supabase schema
- Includes Insert/Update/Select types

**lib/tracking.ts** (Client)
- `getGuestId()`: Gets or creates guest UUID in localStorage
- `trackEvent()`: Logs events to Supabase
- `trackAttempt()`: Records question attempts

### Page Components

**app/page.tsx** (Landing)
- Kyrgyz header + English subtitle
- CTA buttons (Practice, Question Bank)
- 3 feature cards
- Footer

**app/questions/page.tsx** (Question Bank)
- Search by prompt text
- Filters: topic, difficulty, type
- 20 questions per page
- Links to detail view
- Pagination controls

**app/questions/[id]/page.tsx** (Question Detail)
- Full question display with image support
- Show/hide answer button
- Explanation display
- LaTeX formula rendering
- Back button

**app/practice/page.tsx** (Practice Setup)
- Select topic filter
- Select difficulty level
- Choose question count (10/20/30)
- Start button leads to session

**app/practice/session/page.tsx** (Practice Session)
- Full-screen quiz interface
- Progress bar showing completion
- Question display with image support
- MCQ buttons (A, B, C, D)
- Check answer button
- Keyboard shortcuts (1-4, Enter, Esc)
- Time tracking per question
- Answer reveal with explanation
- Next question button
- Results redirect on completion

**app/practice/results/page.tsx** (Results)
- Accuracy percentage with emoji
- Correct/total/incorrect counts
- Visual progress bar
- Encouragement message based on score
- Links to practice again or view dashboard

**app/dashboard/page.tsx** (Analytics)
- 4 stats cards: total, correct, accuracy, streak
- 30-day activity line chart (using Recharts)
- Top 5 topics bar chart
- Recent 10 attempts list
- Sign up prompt for guests

**app/auth/signin/page.tsx** (Sign In)
- Email input field
- Password input field
- Sign in button
- Google OAuth button
- Link to sign up
- Error display

**app/auth/signup/page.tsx** (Sign Up)
- Display name input
- Email input
- Password input (min 6 chars)
- Sign up button
- Google OAuth button
- Link to sign in
- Error display

**app/auth/callback/route.ts** (OAuth Handler)
- GET route for OAuth redirects
- Exchange code for session
- Create user profile if new
- Redirect to dashboard

**app/admin/import/page.tsx** (Admin Import)
- Admin secret input
- JSON file upload
- Import button
- Results display: total/inserted/updated/errors
- Example JSON format shown

**app/api/import/route.ts** (Import API)
- POST endpoint
- Admin secret validation via Authorization header
- JSON parsing and validation
- Upsert logic using source_id
- Flexible field mapping:
  - source_id, id, imported_id
  - prompt, question_kg, question_ky, text
  - correct_answer, answer, correct
  - explanation, explanation_kg, explanation_ky
  - image_url, image
- Response: summary (inserted/updated/errors) + error messages

---

## Data & Seed

**seed-questions.json**
```json
[
  {
    "source_id": "q1",
    "topic": "Алгебра",
    "difficulty": "easy",
    "prompt": "Сан катары сөз айт",
    "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
    "correct_answer": "B",
    "explanation": "Түшүндүрмө"
  }
]
```

Import via:
```bash
curl -X POST http://localhost:3000/api/import \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_SECRET" \
  -d @seed-questions.json
```

---

## Key Features Explained

### Guest Mode
- No sign up needed
- UUID created in localStorage
- Events/attempts tracked with guest_id
- Dashboard shows localStorage-only stats
- Prompt to sign up to save permanently

### Authentication
- Supabase email/password auth
- Google OAuth integration
- Session stored in httpOnly cookies
- `onAuthStateChange` listener detects login/logout
- Profile auto-created on signup

### Practice Mode UX
- **Keyboard Shortcuts**: 1-4 (answer), Enter (check/next), Esc (exit)
- **Fast feedback**: Green for correct, red for wrong, blue for selected
- **Time tracking**: Records seconds spent per question
- **Instant explanation**: Shows after answer check

### Analytics Dashboard
- **Metrics**: Total attempts, correct, accuracy %, streak (days)
- **Charts**: 30-day activity line, topic accuracy bars
- **Recent list**: Last 10 attempts with date and correctness

### Admin Import
- **Validation**: Requires topic, prompt, correct_answer
- **Flexibility**: Supports multiple field naming conventions
- **Upsert**: Updates by source_id if exists, inserts if new
- **Error handling**: Shows first 10 errors for debugging

---

## Environment Variables Reference

| Variable | Example | Where to Get |
|----------|---------|--------------|
| NEXT_PUBLIC_SUPABASE_URL | https://xxxx.supabase.co | Supabase Dashboard > Settings > API |
| NEXT_PUBLIC_SUPABASE_ANON_KEY | eyJ... | Supabase Dashboard > Settings > API |
| SUPABASE_SERVICE_ROLE_KEY | eyJ... | Supabase Dashboard > Settings > API |
| ADMIN_SECRET | my-secret-key-123 | Create your own |

---

## Deployment Checklist

- [ ] All database migrations applied
- [ ] Google OAuth configured in Supabase
- [ ] Environment variables set in hosting platform
- [ ] Seed data imported via `/admin/import`
- [ ] Test all 4 pages
- [ ] Test practice mode with keyboard
- [ ] Test guest mode (localStorage)
- [ ] Test authenticated user flow
- [ ] Build passes: `npm run build`

---

## Testing Checklist

### Landing Page
- [ ] Header displays correctly
- [ ] Both CTA buttons clickable
- [ ] Feature cards visible
- [ ] Responsive on mobile

### Question Bank
- [ ] All questions load
- [ ] Search by text works
- [ ] Topic filter works
- [ ] Difficulty filter works
- [ ] Pagination works
- [ ] Click opens detail page

### Practice Mode
- [ ] Question count selection works
- [ ] Topic/difficulty filters apply
- [ ] Practice session starts
- [ ] Keyboard 1-4 selects answer
- [ ] Enter checks answer
- [ ] Explanation displays
- [ ] Time tracking works
- [ ] Results page shows accuracy
- [ ] Esc exits

### Dashboard
- [ ] Stats cards show numbers
- [ ] Activity chart renders
- [ ] Topic chart renders
- [ ] Recent attempts list shows
- [ ] Guest mode uses localStorage

### Auth
- [ ] Sign up creates account
- [ ] Google OAuth redirects correctly
- [ ] Sign in with email works
- [ ] Sign out clears session
- [ ] Protected routes redirect to signin

---

## Common Customizations

### Change Colors
Edit `app/globals.css`:
```css
:root {
  --background: #0a0a0a;
  --foreground: #ededed;
}
```

### Add/Edit Kyrgyz Text
Search for Kyrgyz strings in `.tsx` files and update:
- Button labels: "Практиканы баштоо"
- Headers: "Суроолор банкы"
- Error messages

### Add Topics
Topics come from database. Just add questions with new topic names.

### Adjust Question Count
In `app/practice/page.tsx`, change button array:
```typescript
{[10, 20, 30, 50].map(count => (...))}
```

---

## Troubleshooting

### "No overload matches this call" TypeScript errors
Use type assertion:
```typescript
const { data } = await (supabase as any).from('table').select('*');
```

### Build fails with prerendering error
Add to client components:
```typescript
export const dynamic = 'force-dynamic';
```

### Google OAuth not redirecting
1. Check Supabase OAuth URLs in Settings > Authentication > Providers
2. Must include `/auth/callback` in redirect URLs
3. Localhost: http://localhost:3000/auth/callback
4. Production: https://yourdomain.com/auth/callback

### Questions not showing
1. Verify migrations ran in Supabase SQL
2. Check Supabase RLS policies are enabled
3. Ensure NEXT_PUBLIC_SUPABASE_URL is correct
4. Import seed data via `/admin/import`

### Analytics not tracking
1. Ensure tracking.ts `trackEvent()` is called
2. Check localStorage has guest_id
3. Verify attempts/events tables have data
4. For auth users, check they're in user_profiles

---

## Performance Tips

- Use pagination (20 per page) to keep questions load fast
- Charts auto-update on page visit (no real-time)
- Images optimized via Next.js Image component
- Recharts handles large datasets well

---

## Security Notes

- ADMIN_SECRET never sent to client
- RLS policies enforce user-only data access
- Service role key never exposed (server-only)
- Google OAuth handled by Supabase
- No passwords logged or displayed

---

## Summary

You now have a complete Kyrgyz math question bank with:
- 4 MVP pages ready to use
- Admin import for your JSON data
- Full analytics dashboard
- Guest + authenticated user support
- Production-ready deployment

To finish:
1. Copy all code files
2. Run migrations
3. Install dependencies
4. Set env vars
5. npm run dev
6. Import your questions
7. Deploy!

Good luck! 🚀
