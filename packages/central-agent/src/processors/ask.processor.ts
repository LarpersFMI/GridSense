import { Processor } from '@nestjs/bullmq';
import { Agent } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { answer } from '../graph/ask';

/**
 * The operator's question about a thread (already on it, from the server): answered from the agent's read-only tools,
 * and the answer added to the thread's conversation. One at a time; it never touches the decision.
 */
@Processor(Agent.Queue.Ask.Definition.name, { concurrency: 1 })
export class AskProcessor extends JobProcessor<typeof Agent.Queue.Ask.Definition> {

    protected readonly definition = Agent.Queue.Ask.Definition;

    protected async handle(job: Agent.Queue.Ask.Job): Promise<{ answered: boolean }> {
        const api = getServerApi();
        const { thread } = await Agent.API.Internal.getThread(api, job.threadId);
        const message = await answer(thread);

        await Agent.API.Internal.addMessage(api, job.threadId, { message });

        return { answered: message.writtenBy === 'llm' };
    }
}
