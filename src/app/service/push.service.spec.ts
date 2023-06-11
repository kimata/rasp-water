import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { PushService } from './push.service';

describe('PushService', () => {
    beforeEach(() =>
        TestBed.configureTestingModule({
            imports: [HttpClientTestingModule],
        })
    );

    it('should be created', () => {
        const service: PushService = TestBed.get(PushService);
        expect(service).toBeTruthy();
    });
});
