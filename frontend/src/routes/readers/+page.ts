import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url, fetch }) => {
  // This file is intentionally left empty as the logic is in +page.server.ts
  // It's here to satisfy TypeScript and SvelteKit's type system
  return {};
};

// Export types that will be used by the page component
export interface Reader {
  id: string;
  name: string;
  title: string;
  rating: number;
  reviews: number;
  specialties: string[];
  rate: number;
  isOnline: boolean;
  image: string;
  languages: string[];
  experience: number;
  bio?: string;
}

export interface PageData {
  readers: Reader[];
  meta: {
    total: number;
    page: number;
    perPage: number;
  };
  filters: {
    search: string;
    specialties: string[];
    minRate: number;
    maxRate: number;
    availableNow: boolean;
    page: number;
  };
  filterOptions: {
    allSpecialties: string[];
    minRate: number;
    maxRate: number;
  };
  error?: {
    status: number;
    message: string;
    code: string;
    stack?: string;
  };
}
