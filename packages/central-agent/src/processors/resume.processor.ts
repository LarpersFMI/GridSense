import { Processor } from '@nestjs/bullmq';
import { Agent } from '@gridsense/shared/domain';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { AgentGraphService } from '../graph/agent-graph.service';

/** An admin's review, from the server: the paused thread resumes from its checkpoint. */
@Processor(Agent.Queue.Resume.Definition.name, { concurrency: 1 })
export class ResumeProcessor extends JobProcessor<typeof Agent.Queue.Resume.Definition> {

    protected readonly definition = Agent.Queue.Resume.Definition;

    constructor(private readonly agent: AgentGraphService) {
        super();
    }

    protected async handle(job: Agent.Queue.Resume.Job): Promise<Agent.Queue.Result> {
        try {
            return { outcome: await this.agent.resume(job.threadId, { decision: job.decision, note: job.note }) };
        }
        catch (error) {
            await this.agent.fail(job.threadId, error);

            throw error;
        }
    }
}
