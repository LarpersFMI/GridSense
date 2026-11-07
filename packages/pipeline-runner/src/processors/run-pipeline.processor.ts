import { Processor } from '@nestjs/bullmq';
import { Pipeline, PipelineRunner, Replay } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { RealtimeService } from '@gridsense/shared/server/realtime';
import { System } from '@gridsense/shared/server/system';
import { PythonService } from '../services/python.service';

/**
 * Runs one pipeline: the run is saved and announced, Python runs it (its lines go out live on the run's channel), and
 * its end — status, rows appended, error, the whole log — is saved and announced. One run at a time: pipelines append
 * to the same files.
 */
@Processor(PipelineRunner.Queue.RunPipeline.Definition.name, { concurrency: 1 })
export class RunPipelineProcessor extends JobProcessor<typeof PipelineRunner.Queue.RunPipeline.Definition> {

    protected readonly definition = PipelineRunner.Queue.RunPipeline.Definition;

    private readonly log = System.log.withContext('RunPipeline');

    constructor(
        private readonly python: PythonService,
        private readonly realtime: RealtimeService,
    ) {
        super();
    }

    protected async handle(job: PipelineRunner.Queue.RunPipeline.Job): Promise<PipelineRunner.Queue.RunPipeline.Result> {
        const api = getServerApi();
        const { run } = await Pipeline.API.Internal.startRun(api, job);

        this.log.info('Started', {
            pipeline: run.pipeline,
            runId:    run.id,
            cause:    run.cause,
        });

        let finish: Pipeline.API.Internal.FinishRun.Request;

        try {
            // The replay's start is set from the UI: the replay pipelines read it as REPLAY_START.
            const { replay } = await Replay.API.Internal.get(api);

            const ended = await this.python.run(run.pipeline, (lines) => {
                this.realtime.emitEvent({
                    ...Pipeline.Event.create('pipeline:run:logged', { runId: run.id, lines }),
                    channel: Pipeline.Event.getRunChannel(run.id),
                });
            }, { REPLAY_START: replay.start });

            let error: string | null = null;

            if (ended.exitCode !== 0)
                error = `Exited with ${ended.exitCode}`;

            finish = {
                status:       ended.exitCode === 0 ? 'succeeded' : 'failed',
                rowsAppended: ended.rowsAppended,
                error,
                log:          ended.log,
            };
        }
        catch (error) {
            finish = {
                status:       'failed',
                rowsAppended: {},
                error:        error instanceof Error ? error.message : String(error),
                log:          '',
            };
        }

        const { run: finished } = await Pipeline.API.Internal.finishRun(api, run.id, finish);

        this.log.info('Finished', {
            pipeline:     finished.pipeline,
            status:       finished.status,
            rowsAppended: finished.rowsAppended,
        });

        return { status: finished.status };
    }
}
