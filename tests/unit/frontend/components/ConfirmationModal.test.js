import { render, screen, fireEvent } from '@testing-library/react';
import ConfirmationModal from '../../../../agent-ui/src/components/ConfirmationModal';

describe('ConfirmationModal', () => {
  test('renders nothing when isOpen is false', () => {
    const { container } = render(
      <ConfirmationModal isOpen={false} title="Test" message="Message" onConfirm={jest.fn()} onCancel={jest.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  test('renders modal when isOpen is true', () => {
    render(
      <ConfirmationModal isOpen={true} title="Confirm Action" message="Are you sure?" onConfirm={jest.fn()} onCancel={jest.fn()} />
    );
    expect(screen.getByText('Confirm Action')).toBeInTheDocument();
    expect(screen.getByText('Are you sure?')).toBeInTheDocument();
  });

  test('calls onConfirm when Confirm button is clicked', () => {
    const mockConfirm = jest.fn();
    render(
      <ConfirmationModal isOpen={true} title="Test" message="Message" onConfirm={mockConfirm} onCancel={jest.fn()} />
    );
    fireEvent.click(screen.getByText('Confirm'));
    expect(mockConfirm).toHaveBeenCalledTimes(1);
  });

  test('calls onCancel when Cancel button is clicked', () => {
    const mockCancel = jest.fn();
    render(
      <ConfirmationModal isOpen={true} title="Test" message="Message" onConfirm={jest.fn()} onCancel={mockCancel} />
    );
    fireEvent.click(screen.getByText('Cancel'));
    expect(mockCancel).toHaveBeenCalledTimes(1);
  });

  test('renders with custom title and message', () => {
    render(
      <ConfirmationModal isOpen={true} title="Delete Account" message="This cannot be undone!" onConfirm={jest.fn()} onCancel={jest.fn()} />
    );
    expect(screen.getByText('Delete Account')).toBeInTheDocument();
    expect(screen.getByText('This cannot be undone!')).toBeInTheDocument();
  });
});
