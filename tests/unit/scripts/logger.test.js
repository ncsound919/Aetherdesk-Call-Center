import { logFrontendError } from '../../../scripts/logger';
jest.spyOn(console, 'error').mockImplementation(() => {});

test('logFrontendError logs to console', () => {
  const error = new Error('Test error');
  logFrontendError(error, { component: 'TestComponent' });
  expect(console.error).toHaveBeenCalled();
});
