import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ locals }) => {
  // This data will be available to all routes
  return {
    // Add any global data that should be available to all routes
    // For example, user session data, site settings, etc.
    user: locals.user || null,
    theme: 'light', // Default theme
    // Add any other global data here
  };
};

// Extend the Session type to include your custom session properties
declare global {
  namespace App {
    interface Locals {
      user?: {
        id: string;
        name: string;
        email: string;
        // Add other user properties as needed
      };
      // Add other custom properties to locals if needed
    }
  }
}
