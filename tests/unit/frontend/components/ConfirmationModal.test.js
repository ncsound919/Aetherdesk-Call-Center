import { render, screen, fireEvent } from '@testing-library/react';
import ConfirmationModal from '../../../../agent-ui/src/components/ConfirmationModal';

test('calls onConfirm when confirm button is clicked', () => {
  const mockConfirm = jest.fn();
  render(<ConfirmationModal isOpen={true} onConfirm={mockConfirm} onCancel={jest.fn()} />);
  fireEvent.click(screen.getByText('Confirm'));
  expect(mockConfirm).toHaveBeenCalledTimes(1);
});
