import { describe, expect, it } from 'vitest';
import { MARKER, PythonOutput } from '../python-output';

const marker = (rowsAppended: Record<string, number>) => `${MARKER}${JSON.stringify({ rowsAppended })}\n`;

describe('PythonOutput', () => {

    it('hands over whole lines and keeps them as the log', () => {
        const output = new PythonOutput();

        expect(output.take('stdout', 'Auction for 2026-11-01: 24 hours\nprices: 24 rows\n')).toEqual([
            'Auction for 2026-11-01: 24 hours',
            'prices: 24 rows',
        ]);
        expect(output.log).toBe('Auction for 2026-11-01: 24 hours\nprices: 24 rows\n');
    });

    it('waits for the rest of a line cut between chunks', () => {
        const output = new PythonOutput();

        expect(output.take('stdout', 'Auction for 20')).toEqual([]);
        expect(output.take('stdout', '26-11-01\nprices')).toEqual(['Auction for 2026-11-01']);
        expect(output.take('stdout', ': 24 rows\n')).toEqual(['prices: 24 rows']);
    });

    it('keeps stdout and stderr apart: a cut line on one is not finished by the other', () => {
        const output = new PythonOutput();

        expect(output.take('stdout', 'half of stdout')).toEqual([]);
        expect(output.take('stderr', 'Traceback (most recent call last):\n')).toEqual(['Traceback (most recent call last):']);
        expect(output.take('stdout', ', the rest\n')).toEqual(['half of stdout, the rest']);
    });

    it('gives the last line at the end, when the output has no final newline', () => {
        const output = new PythonOutput();

        output.take('stderr', 'RuntimeError: no data today');

        expect(output.end('stderr')).toEqual(['RuntimeError: no data today']);
        expect(output.end('stderr')).toEqual([]);
        expect(output.log).toBe('RuntimeError: no data today\n');
    });

    it('counts the rows the markers report, by dataset, and leaves the markers out of the log', () => {
        const output = new PythonOutput();

        const shown = output.take('stdout', `prices: 24 rows\n${marker({ prices: 24 })}${marker({ predictions: 168, prices: 1 })}done\n`);

        expect(shown).toEqual(['prices: 24 rows', 'done']);
        expect(output.rowsAppended).toEqual({ prices: 25, predictions: 168 });
        expect(output.log).not.toContain(MARKER);
    });

    it('reads a marker cut between chunks', () => {
        const output = new PythonOutput();
        const line = marker({ prices: 24 });

        output.take('stdout', line.slice(0, 20));
        output.take('stdout', line.slice(20));

        expect(output.rowsAppended).toEqual({ prices: 24 });
        expect(output.log).toBe('');
    });

    it('nothing appended: no rows, not an error', () => {
        const output = new PythonOutput();

        output.take('stdout', 'prices: nothing new\n');

        expect(output.rowsAppended).toEqual({});
    });

    it('shows a malformed marker instead of throwing: a throw in the stream handler would stop the runner', () => {
        const output = new PythonOutput();

        expect(output.take('stdout', `${MARKER}{"rows": 24}\n${MARKER}not json\n`)).toHaveLength(2);
        expect(output.rowsAppended).toEqual({});
    });
});
