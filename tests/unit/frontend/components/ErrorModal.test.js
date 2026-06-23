import { render, screen, fireEvent } from '@testing-library/react';
import ErrorModal from '../../../../agent-ui/src/components/ErrorModal';

describe('ErrorModal', () => {
  test('renders nothing when isOpen is false', () => {
    const { container } = render(
      <ErrorModal isOpen={false} title="Error" message="Something went wrong" onClose={jest.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  test('renders modal when isOpen is true', () => {
    render(
      <ErrorModal isOpen={true} title="Error" message="Something went wrong" onClose={jest.fn()} />
    );
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  test('calls onClose when OK button is clicked', () => {
    const mockClose = jest.fn();
    render(
      <ErrorModal isOpen={true} title="Error" message="Something went wrong" onClose={mockClose} />
    );
    fireEvent.click(screen.getByText('OK'));
    expect(mockClose).toHaveBeenCalledTimes(1);
  });

  test('renders with custom title and message', () => {
    render(
      <ErrorModal isOpen={true} title="Connection Error" message="Please check your internet" onClose={jest.fn()} />
    );
    expect(screen.getByText('Connection Error')).toBeInTheDocument();
    expect(screen.getByText('Please check your internet')).toBeInTheDocument();
  });
});
