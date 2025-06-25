import { TestBed } from '@angular/core/testing';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { PushService } from './push.service';
import {
    provideHttpClient,
    withInterceptorsFromDi,
} from '@angular/common/http';

describe('PushService', () => {
    beforeEach(() =>
        TestBed.configureTestingModule({
            imports: [],
            providers: [
                provideHttpClient(withInterceptorsFromDi()),
                provideHttpClientTesting(),
            ],
        }),
    );

    it('should be created', () => {
        const service: PushService = TestBed.inject(PushService);
        expect(service).toBeTruthy();
    });
});
