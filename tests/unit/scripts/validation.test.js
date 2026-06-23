import { validateEmail, validateRequired } from '../../../scripts/validation';

describe('validateEmail', () => {
  test('returns true for valid email', () => {
    expect(validateEmail('test@example.com')).toBe(true);
  });

  test('returns true for email with subdomain', () => {
    expect(validateEmail('user@mail.example.com')).toBe(true);
  });

  test('returns true for email with plus', () => {
    expect(validateEmail('user+tag@example.com')).toBe(true);
  });

  test('returns true for email with dots', () => {
    expect(validateEmail('first.last@example.com')).toBe(true);
  });

  test('returns false for email without @', () => {
    expect(validateEmail('invalid-email')).toBe(false);
  });

  test('returns false for email without domain', () => {
    expect(validateEmail('user@')).toBe(false);
  });

  test('returns false for email without TLD', () => {
    expect(validateEmail('user@example')).toBe(false);
  });

  test('returns false for empty string', () => {
    expect(validateEmail('')).toBe(false);
  });

  test('returns false for null', () => {
    expect(validateEmail(null)).toBe(false);
  });

  test('returns false for undefined', () => {
    expect(validateEmail(undefined)).toBe(false);
  });

  test('returns false for email with spaces', () => {
    expect(validateEmail('user @example.com')).toBe(false);
  });

  test('normalizes uppercase to lowercase', () => {
    expect(validateEmail('TEST@EXAMPLE.COM')).toBe(true);
  });
});

describe('validateRequired', () => {
  test('returns true for non-empty string', () => {
    expect(validateRequired('hello')).toBe(true);
  });

  test('returns true for number', () => {
    expect(validateRequired(42)).toBe(true);
  });

  test('returns false for boolean false', () => {
    expect(validateRequired(false)).toBe(false);
  });

  test('returns false for empty string', () => {
    expect(validateRequired('')).toBe(false);
  });

  test('returns false for null', () => {
    expect(validateRequired(null)).toBe(false);
  });

  test('returns false for undefined', () => {
    expect(validateRequired(undefined)).toBe(false);
  });

  test('returns false for zero', () => {
    expect(validateRequired(0)).toBe(false);
  });
});
