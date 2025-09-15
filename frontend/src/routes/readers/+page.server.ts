import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { api } from '$lib/api/client';

export const load: PageServerLoad = async ({ url, fetch }) => {
  try {
    // Get query parameters
    const search = url.searchParams.get('q') || '';
    const specialties = url.searchParams.get('specialties')?.split(',') || [];
    const minRate = url.searchParams.get('minRate') ? Number(url.searchParams.get('minRate')) : undefined;
    const maxRate = url.searchParams.get('maxRate') ? Number(url.searchParams.get('maxRate')) : undefined;
    const availableNow = url.searchParams.get('availableNow') === 'true';
    const page = url.searchParams.get('page') ? Number(url.searchParams.get('page')) : 1;
    const perPage = 12; // Default page size

    // Fetch readers using the API client
    const response = await api.getReaders({
      search,
      specialties,
      minRate,
      maxRate,
      availableNow,
      page,
      perPage
    });

    // Get available filter options
    const filterOptions = {
      allSpecialties: [], // Will be populated by the API in a real app
      minRate: 0,
      maxRate: 100
    };

    return {
      readers: response.data || [],
      meta: response.meta || { total: 0, page, perPage },
      filters: {
        search,
        specialties,
        minRate: minRate || 0,
        maxRate: maxRate || 100,
        availableNow,
        page
      },
      filterOptions
    };
  } catch (err) {
    console.error('Error loading readers:', err);
    
    // Return error state that will be handled by the error boundary
    return {
      readers: [],
      meta: { total: 0, page: 1, perPage: 12 },
      filters: {},
      filterOptions: { allSpecialties: [], minRate: 0, maxRate: 100 },
      error: {
        status: err.status || 500,
        message: err.message || 'Failed to load readers. Please try again later.',
        code: err.code || 'LOAD_ERROR',
        stack: process.env.NODE_ENV === 'development' ? err.stack : undefined
      }
    };
  }
};
