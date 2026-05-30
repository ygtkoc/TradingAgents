# Lucrandos Mobile

Expo-based Android and iOS app for the Lucrandos customer command center.

## Local Setup

Create `frontend/apps/mobile/.env` from `.env.example`:

```bash
EXPO_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=your-public-anon-key
```

Then run:

```bash
cd frontend
pnpm install
pnpm --filter @ta/mobile dev
```

Install Expo Go on a phone and scan the QR code. Android can also run through an emulator with:

```bash
pnpm --filter @ta/mobile android
```

## Builds

Android preview APK:

```bash
cd frontend/apps/mobile
npx eas build --platform android --profile preview
```

iOS TestFlight build:

```bash
cd frontend/apps/mobile
npx eas build --platform ios --profile production
```

iOS publishing requires an Apple Developer account. Android publishing requires a Google Play Console account.
