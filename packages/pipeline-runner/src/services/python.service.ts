import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { Injectable } from '@nestjs/common';
import { Pipeline } from '@gridsense/shared/domain';
import { PythonOutput } from './python-output';

/** Python runs from the repository root, where pyproject.toml and .env are. */
const REPOSITORY_ROOT = resolve(__dirname, '../../../..');

/** How a run ended: its exit code, its whole log, and the rows it appended, by dataset. */
export interface PythonRun {
    exitCode:     number
    log:          string
    rowsAppended: Record<string, number>
}

/**
 * The Python side, as a command line: `<PIPELINE_PYTHON> -m gridsense.pipelines list | run <name>`. PIPELINE_PYTHON
 * is `uv run python` by default; anything that runs the repository's Python works.
 */
@Injectable()
export class PythonService {

    private readonly command = (process.env.PIPELINE_PYTHON ?? 'uv run python').split(/\s+/);

    /** The pipelines Python defines now. */
    public async listPipelines(): Promise<Pipeline[]> {
        let stdout = '';
        let stderr = '';

        const child = spawn(this.command[0], [...this.command.slice(1), '-m', 'gridsense.pipelines', 'list'], { cwd: REPOSITORY_ROOT });

        child.stdout.on('data', (chunk: Buffer) => {
            stdout += chunk.toString();
        });

        child.stderr.on('data', (chunk: Buffer) => {
            stderr += chunk.toString();
        });

        const exitCode = await new Promise<number>((done, fail) => {
            child.on('error', fail);
            child.on('close', (code) => done(code ?? 1));
        });

        if (exitCode !== 0)
            throw new Error(`gridsense.pipelines list exited with ${exitCode}: ${stderr.trim()}`);

        return Pipeline.Schema.array().parse(JSON.parse(stdout));
    }

    /** Runs one pipeline to its end, handing each line it writes (stdout and stderr, markers left out) to `onLines`. */
    public async run(name: Pipeline.Name, onLines: (lines: string[]) => void): Promise<PythonRun> {
        const output = new PythonOutput();

        const child = spawn(this.command[0], [...this.command.slice(1), '-u', '-m', 'gridsense.pipelines', 'run', name], { cwd: REPOSITORY_ROOT });

        const show = (lines: string[]) => {
            if (lines.length > 0)
                onLines(lines);
        };

        child.stdout.on('data', (chunk: Buffer) => show(output.take('stdout', chunk.toString())));
        child.stderr.on('data', (chunk: Buffer) => show(output.take('stderr', chunk.toString())));

        const exitCode = await new Promise<number>((done, fail) => {
            child.on('error', fail);
            child.on('close', (code) => done(code ?? 1));
        });

        show(output.end('stdout'));
        show(output.end('stderr'));

        return {
            exitCode,
            log:          output.log,
            rowsAppended: output.rowsAppended,
        };
    }
}
