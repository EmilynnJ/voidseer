import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { api } from '$lib/api/client';

export const load: PageServerLoad = async ({ fetch }) => {
  try {
    // Fetch featured readers for the homepage
    const featuredReaders = await api.getReaders({
      featured: true,
      perPage: 4
    });

    return {
      featuredReaders: featuredReaders.data || [],
      meta: {
        title: 'SoulSeer - Find Your Perfect Psychic Reader',
        description: 'Connect with experienced psychic readers for live readings, tarot card readings, and spiritual guidance.'
      }
    };
  } catch (err) {
    console.error('Error loading homepage data:', err);
    
    // Return a fallback state that will be handled by the error boundary
    return {
      featuredReaders: [],
      meta: {
        title: 'SoulSeer - Find Your Perfect Psychic Reader',
        description: 'Connect with experienced psychic readers for live readings, tarot card readings, and spiritual guidance.'
      },
      error: {
        status: err.status || 500,
        message: err.message || 'Failed to load homepage data. Please try again later.',
        code: err.code || 'HOMEPAGE_LOAD_ERROR',
        stack: process.env.NODE_ENV === 'development' ? err.stack : undefined
      }
    };
  }
};
