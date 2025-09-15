import { PUBLIC_API_BASE_URL } from '$env/static/public';
import { error } from '@sveltejs/kit';

export interface ApiResponse<T> {
  data: T;
  meta?: {
    total: number;
    page: number;
    perPage: number;
  };
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;
}

export class ApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;

  constructor(baseUrl: string = PUBLIC_API_BASE_URL || 'http://localhost:8000/api') {
    this.baseUrl = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
    
    const headers = {
      ...this.defaultHeaders,
      ...(options.headers || {})
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        credentials: 'include'
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const error: ApiError = new Error(data.message || 'An error occurred') as ApiError;
        error.status = response.status;
        error.code = data.code || 'UNKNOWN_ERROR';
        error.details = data.details;
        throw error;
      }

      return {
        data: data.data,
        meta: data.meta
      };
    } catch (err) {
      if (err instanceof Error) {
        const apiError: ApiError = err as ApiError;
        if (!apiError.status) {
          apiError.status = 500;
          apiError.code = 'NETWORK_ERROR';
          apiError.message = 'Network error occurred. Please check your connection.';
        }
        throw apiError;
      }
      throw error(500, 'An unknown error occurred');
    }
  }

  // Readers API
  async getReaders(params?: {
    search?: string;
    specialties?: string[];
    minRate?: number;
    maxRate?: number;
    availableNow?: boolean;
    page?: number;
    perPage?: number;
  }) {
    const searchParams = new URLSearchParams();
    
    if (params?.search) searchParams.append('search', params.search);
    if (params?.specialties?.length) searchParams.append('specialties', params.specialties.join(','));
    if (params?.minRate !== undefined) searchParams.append('min_rate', params.minRate.toString());
    if (params?.maxRate !== undefined) searchParams.append('max_rate', params.maxRate.toString());
    if (params?.availableNow) searchParams.append('available_now', 'true');
    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.perPage) searchParams.append('per_page', params.perPage.toString());

    const queryString = searchParams.toString();
    return this.request<Array<Reader>>(
      `/readers${queryString ? `?${queryString}` : ''}`
    );
  }

  async getReader(id: string) {
    return this.request<Reader>(`/readers/${id}`);
  }

  // Add other API methods as needed
  // - Authentication
  // - User management
  // - Booking
  // - Payments
  // - etc.
}

// Export a singleton instance
export const api = new ApiClient();

// Types
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
  availability?: {
    timezone: string;
    schedule: Array<{
      day: string;
      slots: Array<{
        start: string;
        end: string;
        available: boolean;
      }>;
    }>;
  };
  // Add other reader properties as needed
}
