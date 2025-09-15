import type { Handle } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';

// Authentication hook
const handleAuth: Handle = async ({ event, resolve }) => {
  // Get the session token from the cookie
  const sessionToken = event.cookies.get('session_token');
  
  if (sessionToken) {
    try {
      // In a real app, you would validate the session token with your auth service
      // For now, we'll just attach a mock user
      event.locals.user = {
        id: 'user-123',
        name: 'Test User',
        email: 'test@example.com',
        // Add other user properties as needed
      };
    } catch (error) {
      // If there's an error validating the token, clear the cookie
      event.cookies.delete('session_token', { path: '/' });
    }
  }

  // Continue with the request
  return resolve(event);
};

// Logging hook
const handleLogging: Handle = async ({ event, resolve }) => {
  const startTime = Date.now();
  const response = await resolve(event);
  const responseTime = Date.now() - startTime;
  
  console.log(`${event.request.method} ${event.url.pathname} - ${response.status} (${responseTime}ms)`);
  
  return response;
};

// Error handling hook
const handleError: Handle = async ({ event, resolve }) => {
  try {
    return await resolve(event);
  } catch (error) {
    console.error('Error handling request:', error);
    
    // In a real app, you might want to log the error to a service like Sentry
    // Sentry.captureException(error);
    
    // Return a custom error response
    return new Response('Internal Server Error', { status: 500 });
  }
};

// Combine all hooks using the sequence helper
export const handle = sequence(handleAuth, handleLogging, handleError);

// Handle server-side errors
export function handleError({ error, event }) {
  console.error('Server-side error:', error);
  
  // In a real app, you might want to log the error to a service like Sentry
  // Sentry.captureException(error);
  
  // Return a custom error response
  return {
    message: 'An unexpected error occurred',
    code: 'UNEXPECTED_ERROR'
  };
}
