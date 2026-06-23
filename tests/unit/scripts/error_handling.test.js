import { mapApiError } from '../../../scripts/error_handling';

describe('mapApiError', () => {
  describe('network errors (no response)', () => {
    test('handles ECONNABORTED timeout', () => {
      const error = { code: 'ECONNABORTED', message: 'timeout of 5000ms exceeded' };
      const result = mapApiError(error);
      expect(result.title).toBe('Request Timed Out');
      expect(result.message).toContain('try again');
    });

    test('handles ETIMEDOUT timeout', () => {
      const error = { code: 'ETIMEDOUT' };
      const result = mapApiError(error);
      expect(result.title).toBe('Request Timed Out');
    });

    test('handles ERR_NETWORK', () => {
      const error = { code: 'ERR_NETWORK', message: 'Network Error' };
      const result = mapApiError(error);
      expect(result.title).toBe('Connection Error');
      expect(result.message).toContain('internet connection');
    });

    test('handles generic network error message', () => {
      const error = { code: undefined, message: 'Network Error occurred' };
      const result = mapApiError(error);
      expect(result.title).toBe('Connection Error');
    });

    test('handles CORS/DNS errors', () => {
      const error = { code: undefined, message: 'Blocked by CORS' };
      const result = mapApiError(error);
      expect(result.title).toBe('Connection Error');
      expect(result.message).toContain('network error');
    });

    test('handles null/undefined error', () => {
      expect(mapApiError(null)).toEqual({ title: 'An Unexpected Error Occurred', message: 'Please contact support if the problem persists.' });
      expect(mapApiError(undefined)).toEqual({ title: 'An Unexpected Error Occurred', message: 'Please contact support if the problem persists.' });
    });
  });

  describe('server errors with mapped codes', () => {
    test('maps INVALID_INPUT with details', () => {
      const error = { response: { data: { error: { code: 'INVALID_INPUT', details: 'email format' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Invalid Input');
      expect(result.message).toContain('email format');
    });

    test('maps INVALID_INPUT without details', () => {
      const error = { response: { data: { error: { code: 'INVALID_INPUT' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Invalid Input');
      expect(result.message).toContain('check your input');
    });

    test('maps SESSION_EXPIRED', () => {
      const error = { response: { data: { error: { code: 'SESSION_EXPIRED' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Session Expired');
      expect(result.requiresAuth).toBe(true);
    });

    test('maps UNAUTHORIZED', () => {
      const error = { response: { data: { error: { code: 'UNAUTHORIZED' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Session Expired');
      expect(result.requiresAuth).toBe(true);
    });

    test('maps FORBIDDEN', () => {
      const error = { response: { data: { error: { code: 'FORBIDDEN' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Access Denied');
      expect(result.message).toContain('permission');
    });

    test('maps CONFLICT code', () => {
      const error = { response: { data: { error: { code: 'CONFLICT' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Update Conflict');
      expect(result.message).toContain('refresh');
    });

    test('maps 409 status code', () => {
      const error = { response: { data: { error: { code: '409' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Update Conflict');
    });

    test('maps RATE_LIMITED', () => {
      const error = { response: { data: { error: { code: 'RATE_LIMITED' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Slow Down');
      expect(result.message).toContain('wait');
    });

    test('maps NOT_FOUND', () => {
      const error = { response: { data: { error: { code: 'NOT_FOUND' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Not Found');
    });

    test('maps NETWORK_ERROR from server', () => {
      const error = { response: { data: { error: { code: 'NETWORK_ERROR' } } } };
      const result = mapApiError(error);
      expect(result.title).toBe('Connection Error');
    });
  });

  describe('HTTP status fallbacks', () => {
    test('falls back to 401 status', () => {
      const error = { response: { status: 401, data: {} } };
      const result = mapApiError(error);
      expect(result.title).toBe('Session Expired');
      expect(result.requiresAuth).toBe(true);
    });

    test('falls back to 403 status', () => {
      const error = { response: { status: 403, data: {} } };
      const result = mapApiError(error);
      expect(result.title).toBe('Access Denied');
    });

    test('falls back to 404 status', () => {
      const error = { response: { status: 404, data: {} } };
      const result = mapApiError(error);
      expect(result.title).toBe('Not Found');
    });

    test('returns generic error for unknown status', () => {
      const error = { response: { status: 500, data: {} } };
      const result = mapApiError(error);
      expect(result.title).toBe('An Unexpected Error Occurred');
    });
  });

  describe('XSS/leak prevention via sanitize()', () => {
    test('strips HTML tags from details', () => {
      const error = { response: { data: { error: { code: 'INVALID_INPUT', details: '<script>alert("xss")</script>' } } } };
      const result = mapApiError(error);
      expect(result.message).not.toContain('<script>');
      expect(result.message).not.toContain('</script>');
    });

    test('escapes quotes in details', () => {
      const error = { response: { data: { error: { code: 'INVALID_INPUT', details: 'value "with" quotes' } } } };
      const result = mapApiError(error);
      expect(result.message).not.toContain('"');
    });

    test('truncates long details to 500 chars', () => {
      const longDetails = 'a'.repeat(1000);
      const error = { response: { data: { error: { code: 'INVALID_INPUT', details: longDetails } } } };
      const result = mapApiError(error);
      expect(result.message.length).toBeLessThan(600);
    });
  });
});
