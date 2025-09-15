import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ data }) => {
  // Shared layout loading logic can go here
  return {
    ...data,
    // Add any layout-specific data here
  };
};

// Export types for the layout data
export interface LayoutData {
  // Add any layout-specific data types here
}
