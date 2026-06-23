import { render, screen, fireEvent } from '@testing-library/react';
import ToastNotification from '../../../../agent-ui/src/components/ToastNotification';

describe('ToastNotification', () => {
  test('renders message', () => {
    render(<ToastNotification message="Success!" onClose={jest.fn()} />);
    expect(screen.getByText('Success!')).toBeInTheDocument();
  });

  test('calls onClose when X button is clicked', () => {
    const mockClose = jest.fn();
    render(<ToastNotification message="Error occurred" onClose={mockClose} />);
    fireEvent.click(screen.getByText('X'));
    expect(mockClose).toHaveBeenCalledTimes(1);
  });

  test('applies default info type class', () => {
    const { container } = render(<ToastNotification message="Info" onClose={jest.fn()} />);
    expect(container.firstChild).toHaveClass('toast', 'toast-info');
  });

  test('applies custom type class', () => {
    const { container } = render(<ToastNotification message="Success" type="success" onClose={jest.fn()} />);
    expect(container.firstChild).toHaveClass('toast', 'toast-success');
  });

  test('applies error type class', () => {
    const { container } = render(<ToastNotification message="Failed" type="error" onClose={jest.fn()} />);
    expect(container.firstChild).toHaveClass('toast', 'toast-error');
  });

  test('renders without onClose button if not provided', () => {
    render(<ToastNotification message="No close" />);
    expect(screen.getByText('No close')).toBeInTheDocument();
    expect(screen.queryByText('X')).toBeNull();
  });
});
