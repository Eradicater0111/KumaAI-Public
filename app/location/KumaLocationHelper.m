#import <AppKit/AppKit.h>
#import <CoreLocation/CoreLocation.h>
#import <Foundation/Foundation.h>
#include <string.h>

// KUMA LOCATION-1 R3 - LAUNCHSERVICES/TCC FOREGROUND LAUNCH

@interface KumaLocationDelegate : NSObject <CLLocationManagerDelegate>
@property(nonatomic, strong) CLLocationManager *manager;
@property(nonatomic, strong) CLGeocoder *geocoder;
@property(nonatomic, strong) NSString *outputPath;
@property(nonatomic, assign) BOOL finished;
@end

@implementation KumaLocationDelegate

- (instancetype)init {
    self = [super init];

    if (self) {
        _manager = [[CLLocationManager alloc] init];
        _manager.delegate = self;
        _manager.desiredAccuracy = kCLLocationAccuracyHundredMeters;
        _finished = NO;
    }

    return self;
}

- (NSString *)authorizationName:(CLAuthorizationStatus)status {
    switch (status) {
        case kCLAuthorizationStatusNotDetermined:
            return @"not_determined";

        case kCLAuthorizationStatusRestricted:
            return @"restricted";

        case kCLAuthorizationStatusDenied:
            return @"denied";

        case kCLAuthorizationStatusAuthorizedAlways:
            // On macOS this also covers the legacy
            // kCLAuthorizationStatusAuthorized value.
            return @"authorized";
    }

    return @"unknown";
}

- (void)finishWithPayload:(NSDictionary *)payload {
    if (self.finished) {
        return;
    }

    self.finished = YES;

    [self.manager stopUpdatingLocation];

    if (self.geocoder != nil) {
        [self.geocoder cancelGeocode];
    }

    NSError *jsonError = nil;

    NSData *data = [
        NSJSONSerialization
        dataWithJSONObject:payload
        options:0
        error:&jsonError
    ];

    if (
        data != nil
        && jsonError == nil
    ) {
        if (
            self.outputPath != nil
            && self.outputPath.length > 0
        ) {
            NSError *writeError = nil;

            BOOL wrote = [
                data
                writeToFile:self.outputPath
                options:NSDataWritingAtomic
                error:&writeError
            ];

            if (!wrote) {
                fprintf(
                    stderr,
                    "KUMA_LOCATION_OUTPUT_WRITE_FAILED: %s\n",
                    (
                        writeError.localizedDescription.UTF8String
                        ?: "unknown"
                    )
                );
            }
        } else {
            NSString *json = [
                [NSString alloc]
                initWithData:data
                encoding:NSUTF8StringEncoding
            ];

            if (json != nil) {
                fprintf(
                    stdout,
                    "%s\n",
                    json.UTF8String
                );
            } else {
                fprintf(
                    stdout,
                    "{\"ok\":false,\"error\":\"encoding_failure\"}\n"
                );
            }
        }
    } else {
        fprintf(
            stderr,
            "KUMA_LOCATION_JSON_FAILURE\n"
        );
    }

    fflush(stdout);
    fflush(stderr);

    // KUMA LOCATION-1 R4 - EXPLICIT NSAPPLICATION TERMINATION
    //
    // The helper is a real foreground NSApplication launched through
    // LaunchServices. Stopping the CFRunLoop does not guarantee that
    // `open -W` observes application termination.
    //
    // The result has already been atomically written and stdio flushed.
    [
        NSApplication.sharedApplication
        terminate:nil
    ];
}

- (void)failWithMessage:(NSString *)message {
    [self finishWithPayload:@{
        @"ok": @NO,
        @"error": (
            message
            ?: @"location_unavailable"
        ),
        @"authorization": [
            self
            authorizationName:
                self.manager.authorizationStatus
        ],
    }];
}

- (void)handleAuthorization {
    CLAuthorizationStatus status = (
        self.manager.authorizationStatus
    );

    switch (status) {
        case kCLAuthorizationStatusNotDetermined:
            [
                NSApplication.sharedApplication
                activateIgnoringOtherApps:YES
            ];

            [
                self.manager
                requestWhenInUseAuthorization
            ];

            return;

        case kCLAuthorizationStatusAuthorizedAlways:
            // macOS uses the authorized/authorizedAlways value.
            [
                self.manager
                requestLocation
            ];

            return;

        case kCLAuthorizationStatusDenied:
            [
                self
                failWithMessage:
                    @"location_permission_denied"
            ];

            return;

        case kCLAuthorizationStatusRestricted:
            [
                self
                failWithMessage:
                    @"location_permission_restricted"
            ];

            return;
    }

    [
        self
        failWithMessage:
            @"unknown_authorization_status"
    ];
}

- (void)start {
    if (
        ![
            CLLocationManager
            locationServicesEnabled
        ]
    ) {
        [
            self
            failWithMessage:
                @"location_services_disabled"
        ];

        return;
    }

    [
        self
        handleAuthorization
    ];
}

- (void)timeout {
    if (self.finished) {
        return;
    }

    [
        self
        failWithMessage:
            @"location_request_timed_out"
    ];
}

- (void)locationManagerDidChangeAuthorization:
    (CLLocationManager *)manager
{
    if (self.finished) {
        return;
    }

    [
        self
        handleAuthorization
    ];
}

- (void)locationManager:
    (CLLocationManager *)manager
    didFailWithError:
    (NSError *)error
{
    NSString *message = [
        @"location_update_failed: "
        stringByAppendingString:
            (
                error.localizedDescription
                ?: @"unknown_error"
            )
    ];

    [
        self
        failWithMessage:
            message
    ];
}

- (void)locationManager:
    (CLLocationManager *)manager
    didUpdateLocations:
    (NSArray<CLLocation *> *)locations
{
    if (self.finished) {
        return;
    }

    CLLocation *location = nil;

    for (
        CLLocation *candidate
        in locations.reverseObjectEnumerator
    ) {
        if (
            candidate.horizontalAccuracy
            >= 0
        ) {
            location = candidate;
            break;
        }
    }

    if (location == nil) {
        [
            self
            failWithMessage:
                @"no_valid_location"
        ];

        return;
    }

    NSISO8601DateFormatter *formatter = (
        [[NSISO8601DateFormatter alloc] init]
    );

    NSMutableDictionary *payload = [
        @{
            @"ok": @YES,
            @"latitude": @(
                location.coordinate.latitude
            ),
            @"longitude": @(
                location.coordinate.longitude
            ),
            @"horizontal_accuracy_m": @(
                location.horizontalAccuracy
            ),
            @"altitude_m": @(
                location.altitude
            ),
            @"timestamp": (
                [
                    formatter
                    stringFromDate:
                        location.timestamp
                ]
                ?: @""
            ),
            @"authorization": [
                self
                authorizationName:
                    self.manager.authorizationStatus
            ],
        }
        mutableCopy
    ];

    // LOCATION-1 returns locality-level metadata only.
    // Precise street-address resolution remains reserved for ADDRESS-1.
    self.geocoder = (
        [[CLGeocoder alloc] init]
    );

    __weak typeof(self) weakSelf = self;

    [
        self.geocoder
        reverseGeocodeLocation:location
        completionHandler:
            ^(
                NSArray<CLPlacemark *> *placemarks,
                NSError *error
            ) {
                KumaLocationDelegate *strongSelf = (
                    weakSelf
                );

                if (strongSelf == nil) {
                    return;
                }

                CLPlacemark *placemark = (
                    placemarks.firstObject
                );

                if (placemark != nil) {
                    // KUMA LOCATION-2: native result may carry postal
                    // components, but Python exposes them only when the
                    // current request explicitly grounds detail="address".
                    if (placemark.subThoroughfare.length > 0) {
                        payload[@"street_number"] = (
                            placemark.subThoroughfare
                        );
                    }

                    if (placemark.thoroughfare.length > 0) {
                        payload[@"street"] = (
                            placemark.thoroughfare
                        );
                    }

                    if (placemark.subLocality.length > 0) {
                        payload[@"sub_locality"] = (
                            placemark.subLocality
                        );
                    }

                    if (placemark.postalCode.length > 0) {
                        payload[@"postal_code"] = (
                            placemark.postalCode
                        );
                    }

                    if (placemark.locality.length > 0) {
                        payload[@"locality"] = (
                            placemark.locality
                        );
                    }

                    if (
                        placemark
                        .administrativeArea
                        .length
                        > 0
                    ) {
                        payload[
                            @"administrative_area"
                        ] = (
                            placemark
                            .administrativeArea
                        );
                    }

                    if (placemark.country.length > 0) {
                        payload[@"country"] = (
                            placemark.country
                        );
                    }

                    if (
                        placemark
                        .ISOcountryCode
                        .length
                        > 0
                    ) {
                        payload[
                            @"iso_country_code"
                        ] = (
                            placemark
                            .ISOcountryCode
                        );
                    }
                }

                [
                    strongSelf
                    finishWithPayload:
                        payload
                ];
            }
    ];
}

@end


int main(
    int argc,
    const char *argv[]
) {
    @autoreleasepool {
        NSApplication *app = (
            NSApplication.sharedApplication
        );

        [
            app
            setActivationPolicy:
                NSApplicationActivationPolicyRegular
        ];

        [
            app
            finishLaunching
        ];

        [
            app
            activateIgnoringOtherApps:YES
        ];

        NSString *outputPath = nil;

        for (
            int index = 1;
            index + 1 < argc;
            index += 1
        ) {
            if (
                strcmp(
                    argv[index],
                    "--output"
                )
                == 0
            ) {
                outputPath = [
                    NSString
                    stringWithUTF8String:
                        argv[
                            index + 1
                        ]
                ];

                break;
            }
        }

        KumaLocationDelegate *delegate = (
            [[KumaLocationDelegate alloc] init]
        );

        delegate.outputPath = (
            outputPath
        );

        dispatch_async(
            dispatch_get_main_queue(),
            ^{
                [
                    delegate
                    start
                ];
            }
        );

        dispatch_after(
            dispatch_time(
                DISPATCH_TIME_NOW,
                (int64_t)(
                    18.0
                    * NSEC_PER_SEC
                )
            ),
            dispatch_get_main_queue(),
            ^{
                [
                    delegate
                    timeout
                ];
            }
        );

        [
            NSRunLoop.currentRunLoop
            run
        ];
    }

    return 0;
}
