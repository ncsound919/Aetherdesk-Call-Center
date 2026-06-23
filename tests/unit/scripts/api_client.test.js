/**
 * Tests for the axios API client interceptor.
 *
 * Because the interceptor is registered during module load, we mock axios
 * and capture the error handler that is passed to interceptors.response.use().
 * We then invoke that handler directly to verify that errors are mapped
 * and rejected correctly.
 */

let capturedErrorHandler;

jest.mock('axios', () => {
  const mockInterceptors = {
    response: {
      use: jest.fn((_successFn, errorHandler) => {
        capturedErrorHandler = errorHandler;
      }),
    },
  };
  return {
    __esModule: true,
    default: {
      create: jest.fn(() => ({
        interceptors: mockInterceptors,
        get: jest.fn(),
        post: jest.fn(),
      })),
    },
  };
});

jest.mock('../../../scripts/error_handling', () => ({
  mapApiError: jest.fn((err) => {
    // Simple real-ish implementation for the interceptor test
    if (!err.response) {
      return { title: 'Connection Error', message: 'Network error.' };
    }
    const code = err.response?.data?.error?.code;
    return { title: code || 'Unknown Error', message: 'Something went wrong.' };
  }),
}));

// Force a fresh import so the interceptor registration runs with our mocks.
beforeEach(() => {
  jest.resetModules();
  capturedErrorHandler = undefined;
  require('../../../scripts/api_client');
});

describe('apiClient interceptor', () => {
  test('rejects with the mapped error object', async () => {
    const networkError = new Error('Network Error');
    networkError.request = {};
    networkError.response = undefined;

    const result = capturedErrorHandler(networkError);
    expect(result).toBeInstanceOf(Promise);

    await expect(result).rejects.toEqual(
      expect.objectContaining({
        title: 'Connection Error',
        message: 'Network error.',
      })
    );
  });

  test('passes through mapped server error with status', async () => {
    const serverError = {
      response: { status: 500, data: { error: { code: 'INTERNAL' } } },
      request: {},
    };

    await expect(capturedErrorHandler(serverError)).rejects.toEqual(
      expect.objectContaining({ title: 'INTERNAL' })
    );
  });

  test('returns the original response unchanged on success', () => {
    // The success handler is the identity function (response => response).
    jest.resetModules();
    let capturedSuccessHandler;
    const mockInterceptors = {
      response: {
        use: jest.fn((successFn) => {
          capturedSuccessHandler = successFn;
        }),
      },
    };
    jest.doMock('axios', () => ({
      __esModule: true,
      default: { create: jest.fn(() => ({ interceptors: mockInterceptors })) },
    }));
    jest.doMock('../../../scripts/error_handling', () => ({ mapApiError: jest.fn() }));
    require('../../../scripts/api_client');

    const fakeResponse = { data: { ok: true }, status: 200 };
    expect(capturedSuccessHandler(fakeResponse)).toBe(fakeResponse);
  });
});
