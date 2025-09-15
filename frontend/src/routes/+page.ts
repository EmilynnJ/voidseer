import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
  // Client-side loading logic can go here if needed
  return {};
};

// Export types for the page data
export interface PageData {
  featuredReaders: Array<{
    id: string;
    name: string;
    title: string;
    rating: number;
    reviews: number;
    specialties: string[];
    rate: number;
    isOnline: boolean;
    image: string;
    bio?: string;
  }>;
  meta?: {
    title: string;
    description: string;
  };
  error?: {
    status: number;
    message: string;
    code: string;
    stack?: string;
  };
}
