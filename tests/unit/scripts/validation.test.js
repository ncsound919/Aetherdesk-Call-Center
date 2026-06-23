import { validateEmail, validateRequired } from '../../../scripts/validation';

test('validateEmail returns true for valid email', () => {
  expect(validateEmail('test@example.com')).toBe(true);
});
test('validateEmail returns false for invalid email', () => {
  expect(validateEmail('invalid-email')).toBe(false);
});
