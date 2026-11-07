import { rmSync } from 'node:fs';
import { dirname } from 'node:path';
import { BadRequestException, Injectable } from '@nestjs/common';
import { Queue } from 'bullmq';
import { Agent, Dataset, Pipeline, PipelineRunner, Replay, Time } from '@gridsense/shared/domain';
import { getDatasetPath } from '@gridsense/shared/server/datasets';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { QUEUE_PREFIX, redisConnection, sharedRedis } from '@gridsense/shared/server/redis';
import { System } from '@gridsense/shared/server/system';
import { DatasetService } from '../Dataset/dataset.service';
import { ReplayRepository } from './replay.repository';

// The replay's pipelines (gridsense.pipelines.replay): a step runs them in this order.
const PIPELINES: Pipeline.Name[] = ['forecast', 'prices'];

// The Watchdog's cooldown keys (HitService.raise).
const COOLDOWNS = 'gridsense:watchdog:cooldown:*';

const DAY_MS = 24 * 60 * 60_000;
const HOUR_MS = 60 * 60_000;

/**
 * The replay: its start (one row), where it is (the dataset files), a step (`forecast` then `prices`) and a reset —
 * so the demo can be rehearsed from the same day as often as needed.
 */
@Injectable()
export class ReplayService {

    private readonly log = System.log.withContext('Replay');

    constructor(
        private readonly replay: ReplayRepository,
        private readonly datasets: DatasetService,
        private readonly queues: QueueProducer,
    ) {}

    public async get(): Promise<Replay.State> {
        const replay = await this.replay.get();
        const issued = await this.datasets.getLatest('predictions', 'issue_ts');
        const cleared = await this.datasets.getLatest('prices', 'ts_utc');

        return {
            ...replay,
            issued:  issued === null ? null : Time.Local.of(issued).day,
            cleared: cleared === null ? null : Time.Local.of(cleared).day,
            range:   {
                from: Replay.RANGES.validation.from,
                to:   process.env.ALLOW_TEST_REPLAY === '1' ? Replay.RANGES.test.to : Replay.RANGES.validation.to,
            },
        };
    }

    public async setStart(start: Replay.LocalDate): Promise<Replay.State> {
        const { range } = await this.get();

        if (start < range.from || start > range.to)
            throw new BadRequestException(`The replay starts between ${range.from} and ${range.to}${process.env.ALLOW_TEST_REPLAY === '1' ? '' : ' (the test split opens with ALLOW_TEST_REPLAY=1, once evaluated)'}`);

        await this.replay.setStart(start);

        return this.reset();
    }

    public async reset(): Promise<Replay.State> {
        const folder = dirname(getDatasetPath('predictions'));

        // The team's own tables live in data/processed: a reset removes files, never those.
        if (folder.endsWith('/data/processed'))
            throw new BadRequestException(`DATASET_DIR is the team's data folder (${folder}): the replay resets only its own (data/replay)`);

        const { start } = await this.replay.get();

        for (const name of Dataset.Name.options)
            rmSync(getDatasetPath(name), { force: true });

        // The first `prices` run adds the history up to the start day's end: the triggers on prices read past it.
        const nextDay = new Date(Date.parse(`${start}T12:00:00Z`) + DAY_MS).toISOString().slice(0, 10);

        await this.replay.setWatermarks({
            predictions: null,
            prices:      new Date(Time.Local.startOfDay(nextDay).getTime() - HOUR_MS),
        });
        await this.replay.deleteRuns(PIPELINES);

        for (const definition of [Agent.Queue.HandleHit.Definition, Agent.Queue.Resume.Definition]) {
            const queue = new Queue(definition.name, { connection: redisConnection(), prefix: QUEUE_PREFIX });

            await queue.obliterate({ force: true });
            await queue.close();
        }

        const redis = sharedRedis();
        const cooldowns = await redis.keys(COOLDOWNS);

        if (cooldowns.length > 0)
            await redis.del(...cooldowns);

        this.log.info('Reset', { start, folder, cooldowns: cooldowns.length });

        return this.get();
    }

    /** One day of the replay: the forecast is issued, then the auction clears. */
    public async step(): Promise<void> {
        for (const pipeline of PIPELINES)
            await this.queues.add(PipelineRunner.Queue.RunPipeline.Definition, { pipeline, cause: 'manual' });
    }
}
