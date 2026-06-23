import { mapApiError } from '../../../scripts/error_handling';

test('maps INVALID_INPUT error correctly', () => {
  const error = { response: { data: { error: { code: 'INVALID_INPUT', details: 'email format' } } } };
  expect(mapApiError(error)).toEqual({ title: 'Invalid Input', message: 'Please check your input: email format' });
});
