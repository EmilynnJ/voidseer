// Base API response type
export interface ApiResponse<T> {
  data: T;
  message?: string;
  success: boolean;
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  meta?: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
}

// User related types
export interface User {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  role: 'user' | 'reader' | 'admin';
  isEmailVerified: boolean;
  createdAt: string;
  updatedAt: string;
}

// Reader profile type
export interface ReaderProfile extends User {
  bio: string;
  specialties: string[];
  rating: number;
  totalReadings: number;
  isAvailable: boolean;
  languages: string[];
  experience: number; // in years
  pricePerMinute: number;
  isFavorite?: boolean;
  readingMethods: {
    type: 'chat' | 'video' | 'audio' | 'in-person';
    isAvailable: boolean;
  }[];
}

// Reading session type
export interface ReadingSession {
  id: string;
  readerId: string;
  userId: string;
  startTime: string;
  endTime?: string;
  duration: number; // in minutes
  status: 'pending' | 'in-progress' | 'completed' | 'cancelled';
  paymentStatus: 'pending' | 'paid' | 'refunded' | 'failed';
  amount: number;
  currency: string;
  notes?: string;
  rating?: number;
  review?: string;
  reader: Pick<ReaderProfile, 'id' | 'name' | 'avatar'>;
  user: Pick<User, 'id' | 'name' | 'email'>;
}

// Chat message type
export interface ChatMessage {
  id: string;
  sessionId: string;
  senderId: string;
  senderType: 'user' | 'reader';
  content: string;
  timestamp: string;
  isRead: boolean;
}

// Payment method type
export interface PaymentMethod {
  id: string;
  type: 'card' | 'paypal' | 'apple-pay' | 'google-pay';
  last4?: string;
  brand?: string;
  isDefault: boolean;
  expiresAt?: string;
}

// Notification type
export interface Notification {
  id: string;
  userId: string;
  type: 'info' | 'success' | 'warning' | 'error' | 'message' | 'reading';
  title: string;
  message: string;
  isRead: boolean;
  link?: string;
  createdAt: string;
}

// Filter options for readers
export interface ReaderFilters {
  specialties?: string[];
  minRating?: number;
  maxPrice?: number;
  languages?: string[];
  isAvailableNow?: boolean;
  readingMethods?: string[];
  experienceMin?: number;
  experienceMax?: number;
  sortBy?: 'rating' | 'price' | 'experience' | 'newest';
  sortOrder?: 'asc' | 'desc';
  searchQuery?: string;
  page?: number;
  limit?: number;
}
