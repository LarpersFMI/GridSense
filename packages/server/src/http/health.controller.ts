import { Controller, Get } from '@nestjs/common';

/** For the workers' waitForServer and container probes. */
@Controller('api/health')
export class HealthController {

    @Get()
    public health() {
        return { ok: true };
    }
}
