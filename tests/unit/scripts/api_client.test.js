import apiClient from '../../../scripts/api_client';
import { mapApiError } from '../../../scripts/error_handling';

// Mock axios
jest.mock('axios', () => ({
  create: jest.fn(() => ({
    interceptors: { response: { use: jest.fn() } },
    get: jest.fn(),
  })),
}));
jest.mock('../../../scripts/error_handling', () => ({
  mapApiError: jest.fn(),
}));

// ... Test interceptor mapping (mocked axios implementation required)
