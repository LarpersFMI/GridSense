import { Body, Controller, Get, HttpCode, Param, Post, Put, Query } from '@nestjs/common';
import { Agent, Foundations } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { AgentService } from '../agent.service';

import Internal = Agent.API.Internal;

/** For the central agent: its threads as they move, the slots it reads and writes, its graph. */
@Controller('internal/agent')
export class AgentInternalHttpController {

    constructor(private readonly service: AgentService) {}

    @Put('threads/:id')
    public async saveThread(
        @Param('id', new ZodPipe(Foundations.Thread.Id)) _id: Foundations.Thread.Id,
        @Body(new ZodPipe(Internal.SaveThread.Request)) request: Internal.SaveThread.Request,
    ): Promise<Internal.SaveThread.Response> {
        return { thread: await this.service.saveThread(request.thread) };
    }

    @Post('threads/:id/messages')
    public async addMessage(
        @Param('id', new ZodPipe(Foundations.Thread.Id)) id: Foundations.Thread.Id,
        @Body(new ZodPipe(Internal.AddMessage.Request)) request: Internal.AddMessage.Request,
    ): Promise<Internal.SaveThread.Response> {
        return { thread: await this.service.addMessage(id, request.message) };
    }

    @Get('threads/:id')
    public async getThread(@Param('id', new ZodPipe(Foundations.Thread.Id)) id: Foundations.Thread.Id): Promise<Internal.SaveThread.Response> {
        return { thread: await this.service.getThread(id) };
    }

    @Get('slots')
    public async listSlots(@Query(new ZodPipe(Internal.ListSlots.Query)) query: Internal.ListSlots.Query): Promise<Internal.ListSlots.Response> {
        return { slots: await this.service.listSlots(query) };
    }

    @Put('slots/:key')
    public async saveSlot(@Body(new ZodPipe(Internal.SaveSlot.Request)) request: Internal.SaveSlot.Request): Promise<Internal.SaveSlot.Response> {
        return { slot: await this.service.saveSlot(request.slot) };
    }

    @Put('graph')
    @HttpCode(204)
    public async saveGraph(@Body(new ZodPipe(Internal.SaveGraph.Request)) request: Internal.SaveGraph.Request): Promise<void> {
        await this.service.saveGraph(request.graph);
    }
}
