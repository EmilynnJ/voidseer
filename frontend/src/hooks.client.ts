import { browser } from '$app/environment';
import { PUBLIC_SENTRY_DSN } from '$env/static/public';
import * as Sentry from '@sentry/svelte';
import type { HandleClientError } from '@sveltejs/kit';

// Initialize client-side error tracking if in production
if (browser && import.meta.env.PROD && PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: PUBLIC_SENTRY_DSN,
    environment: import.meta.env.MODE,
    integrations: [
      new Sentry.BrowserTracing({
        // Set 'tracePropagationTargets' to control for which URLs distributed tracing should be enabled
        tracePropagationTargets: ['localhost', /^https:\/\/api\.soulseer\.com\/api/],
      }),
      new Sentry.Replay(),
    ],
    // Performance Monitoring
    tracesSampleRate: 1.0, // Capture 100% of transactions for performance monitoring
    // Session Replay
    replaysSessionSampleRate: 0.1, // This sets the sample rate at 10%
    replaysOnErrorSampleRate: 1.0, // If you're not already sampling the entire session, change the sample rate to 100% when sampling sessions where errors occur.
  });
}

// Handle client-side errors
export const handleError: HandleClientError = ({ error, event }) => {
  const errorId = crypto.randomUUID();
  
  // Log the error to the console in development
  if (import.meta.env.DEV) {
    console.error('Client-side error:', error);
  }
  
  // In production, send the error to Sentry
  if (browser && import.meta.env.PROD && PUBLIC_SENTRY_DSN) {
    Sentry.captureException(error, { contexts: { sveltekit: { event, errorId } } });
  }
  
  // Return a user-friendly error message
  return {
    message: 'An unexpected error occurred',
    errorId,
  };
};

// Track page views for analytics
export const handleTrack = (url: URL) => {
  if (browser && import.meta.env.PROD) {
    // In a real app, you would send this to your analytics service
    // Example: trackPageView(url.pathname);
    console.log(`Page view: ${url.pathname}`);
  }
};
