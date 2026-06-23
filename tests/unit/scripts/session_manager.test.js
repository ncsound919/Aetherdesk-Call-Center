import { createUndoManager } from '../../../scripts/session_manager';

describe('createUndoManager', () => {
  let manager;

  beforeEach(() => {
    manager = createUndoManager();
  });

  describe('perform()', () => {
    test('executes action and records history', async () => {
      const action = jest.fn(() => 'result');
      const undo = jest.fn();

      const result = await manager.perform(action, undo, 'arg1');
      expect(result).toBe('result');
      expect(action).toHaveBeenCalledWith('arg1');
      expect(manager.length()).toBe(1);
    });

    test('does not record failed actions', async () => {
      const failingAction = jest.fn(() => { throw new Error('fail'); });
      const undo = jest.fn();

      await expect(manager.perform(failingAction, undo)).rejects.toThrow('fail');
      expect(manager.length()).toBe(0);
    });

    test('throws TypeError if undoFn is not provided', async () => {
      const action = jest.fn(() => 'ok');
      await expect(manager.perform(action)).rejects.toThrow(TypeError);
    });

    test('throws TypeError if undoFn is not a function', async () => {
      const action = jest.fn(() => 'ok');
      await expect(manager.perform(action, 'not a function')).rejects.toThrow(TypeError);
    });

    test('throws TypeError if actionFn is not a function', async () => {
      const undo = jest.fn();
      await expect(manager.perform('not a function', undo)).rejects.toThrow(TypeError);
    });

    test('passes all args to actionFn', async () => {
      const action = jest.fn(() => 'ok');
      const undo = jest.fn();
      await manager.perform(action, undo, 'a', 'b', 'c');
      expect(action).toHaveBeenCalledWith('a', 'b', 'c');
    });
  });

  describe('undo()', () => {
    test('undoes the most recent action', async () => {
      const action = jest.fn(() => 'result');
      const undoFn = jest.fn();
      await manager.perform(action, undoFn, 'arg1');

      const entry = await manager.undo();
      expect(undoFn).toHaveBeenCalledWith('result', 'arg1');
      expect(entry).toEqual({ undoFn, args: ['arg1'], result: 'result' });
    });

    test('returns null when history is empty', async () => {
      const result = await manager.undo();
      expect(result).toBeNull();
    });

    test('handles async undo functions', async () => {
      const action = jest.fn(() => 'result');
      const asyncUndo = jest.fn(async () => { await Promise.resolve(); });
      await manager.perform(action, asyncUndo);

      const entry = await manager.undo();
      expect(asyncUndo).toHaveBeenCalled();
      expect(entry).toBeDefined();
    });

    test('re-pushes entry if undo fails', async () => {
      const action = jest.fn(() => 'result');
      const failingUndo = jest.fn(() => { throw new Error('undo failed'); });
      await manager.perform(action, failingUndo);

      await expect(manager.undo()).rejects.toThrow('undo failed');
      expect(manager.length()).toBe(1);
    });
  });

  describe('clear()', () => {
    test('clears history', async () => {
      await manager.perform(jest.fn(() => 'ok'), jest.fn());
      await manager.perform(jest.fn(() => 'ok'), jest.fn());
      expect(manager.length()).toBe(2);

      manager.clear();
      expect(manager.length()).toBe(0);
    });
  });

  describe('length()', () => {
    test('tracks history length accurately', async () => {
      expect(manager.length()).toBe(0);
      await manager.perform(jest.fn(() => 'ok'), jest.fn());
      expect(manager.length()).toBe(1);
      await manager.perform(jest.fn(() => 'ok'), jest.fn());
      expect(manager.length()).toBe(2);
      await manager.undo();
      expect(manager.length()).toBe(1);
    });
  });

  describe('maxHistory', () => {
    test('respects max history limit', async () => {
      const boundedManager = createUndoManager(3);
      await boundedManager.perform(jest.fn(() => 'a'), jest.fn());
      await boundedManager.perform(jest.fn(() => 'b'), jest.fn());
      await boundedManager.perform(jest.fn(() => 'c'), jest.fn());
      await boundedManager.perform(jest.fn(() => 'd'), jest.fn());

      expect(boundedManager.length()).toBe(3);
    });

    test('drops oldest entries when at capacity', async () => {
      const boundedManager = createUndoManager(2);
      const undo1 = jest.fn();
      const undo2 = jest.fn();
      const undo3 = jest.fn();

      await boundedManager.perform(jest.fn(() => 'a'), undo1);
      await boundedManager.perform(jest.fn(() => 'b'), undo2);
      await boundedManager.perform(jest.fn(() => 'c'), undo3);

      // Should undo the most recent (c), then (b). (a) should be dropped.
      await boundedManager.undo();
      expect(undo3).toHaveBeenCalled();
      await boundedManager.undo();
      expect(undo2).toHaveBeenCalled();
      expect(undo1).not.toHaveBeenCalled();
    });
  });
});
