import { logFrontendError } from '../../../scripts/logger';

describe('logFrontendError', () => {
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('logs error to console', () => {
    const error = new Error('Test error');
    logFrontendError(error, { component: 'TestComponent' });
    expect(console.error).toHaveBeenCalledWith('Frontend Error:', error, { component: 'TestComponent' });
  });

  test('logs with empty context', () => {
    const error = new Error('Another error');
    logFrontendError(error, {});
    expect(console.error).toHaveBeenCalled();
  });

  test('logs with null context', () => {
    const error = new Error('Null context error');
    logFrontendError(error, null);
    expect(console.error).toHaveBeenCalled();
  });

  test('logs string errors', () => {
    logFrontendError('string error', { page: 'home' });
    expect(console.error).toHaveBeenCalled();
  });

  test('logs object errors', () => {
    logFrontendError({ code: 500, message: 'Server Error' }, { action: 'fetch' });
    expect(console.error).toHaveBeenCalled();
  });
});
