import { z } from 'zod';

/** A line a pipeline prints to tell the runner something, not for people: `@@gridsense {"rowsAppended": {"prices": 24}}`. */
export const MARKER = '@@gridsense ';

const Report = z.object({ rowsAppended: z.record(z.string(), z.number().int().nonnegative()) });

/**
 * A run's output as it arrives, in chunks that may end mid-line, from stdout and stderr: cut into lines, markers
 * taken out and counted, the rest kept as the log.
 */
export class PythonOutput {

    public log = '';

    public readonly rowsAppended: Record<string, number> = {};

    private readonly partial = { stdout: '', stderr: '' };

    /** The chunk's whole lines for people (markers left out); an unfinished one waits for the next chunk or `end`. */
    public take(stream: 'stdout' | 'stderr', chunk: string): string[] {
        const lines = (this.partial[stream] + chunk).split('\n');

        this.partial[stream] = lines.pop() ?? '';

        return this.keep(lines);
    }

    /** The stream's last line, if it didn't end with a newline. */
    public end(stream: 'stdout' | 'stderr'): string[] {
        const last = this.partial[stream];

        this.partial[stream] = '';

        return this.keep(last === '' ? [] : [last]);
    }

    private keep(lines: string[]): string[] {
        const shown: string[] = [];

        for (const line of lines) {
            if (!line.startsWith(MARKER)) {
                shown.push(line);
                continue;
            }

            // Thrown here, in a stream's 'data' handler, it would bring the whole runner down: shown instead.
            const report = Report.safeParse(safeJson(line.slice(MARKER.length)));

            if (!report.success) {
                shown.push(`${line}  ← not a marker the runner reads: ignored`);
                continue;
            }

            for (const [dataset, rows] of Object.entries(report.data.rowsAppended))
                this.rowsAppended[dataset] = (this.rowsAppended[dataset] ?? 0) + rows;
        }

        if (shown.length > 0)
            this.log += `${shown.join('\n')}\n`;

        return shown;
    }
}

function safeJson(text: string): unknown {
    try {
        return JSON.parse(text);
    }
    catch {
        return null;
    }
}
