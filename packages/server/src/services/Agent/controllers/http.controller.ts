import { Body, Controller, Get, Header, HttpCode, Param, Post, Query } from '@nestjs/common';
import { Agent, Foundations } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { AgentService } from '../agent.service';

import API = Agent.API;

/** For the browser: the agent's threads and inbox, an admin's review, the slots, the graph, the calendar file. */
@Controller('api/agent')
export class AgentHttpController {

    constructor(private readonly service: AgentService) {}

    @Get('threads')
    public listThreads(@Query(new ZodPipe(API.ListThreads.Query)) query: API.ListThreads.Query): Promise<API.ListThreads.Response> {
        return this.service.listThreads(query);
    }

    @Get('threads/:id')
    public async getThread(@Param('id', new ZodPipe(Foundations.Thread.Id)) id: Foundations.Thread.Id): Promise<API.GetThread.Response> {
        return { thread: await this.service.getThread(id) };
    }

    @Post('threads/:id/review')
    @HttpCode(202)
    public async review(
        @Param('id', new ZodPipe(Foundations.Thread.Id)) id: Foundations.Thread.Id,
        @Body(new ZodPipe(API.Review.Request)) request: API.Review.Request,
    ): Promise<API.Review.Response> {
        await this.service.review(id, request);

        return { queued: true };
    }

    @Post('threads/:id/questions')
    @HttpCode(202)
    public async ask(
        @Param('id', new ZodPipe(Foundations.Thread.Id)) id: Foundations.Thread.Id,
        @Body(new ZodPipe(API.Ask.Request)) request: API.Ask.Request,
    ): Promise<API.Ask.Response> {
        await this.service.ask(id, request.question);

        return { queued: true };
    }

    @Get('slots')
    public async listSlots(@Query(new ZodPipe(API.ListSlots.Query)) query: API.ListSlots.Query): Promise<API.ListSlots.Response> {
        return { slots: await this.service.listSlots({ from: query.from }) };
    }

    @Get('graph')
    public async getGraph(): Promise<API.GetGraph.Response> {
        return { graph: await this.service.getGraph() };
    }

    @Get('calendar.ics')
    @Header('content-type', 'text/calendar; charset=utf-8')
    @Header('content-disposition', 'attachment; filename="gridsense-zero-cost-hours.ics"')
    public getCalendar(): Promise<string> {
        return this.service.getCalendar();
    }
}
