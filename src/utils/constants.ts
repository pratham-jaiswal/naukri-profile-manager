// Login URL
export const loginUrl =
  'https://www.naukri.com/central-login-services/v1/login';

// Resume upload URL
export const resumeUploadUrl = 'https://filevalidation.naukri.com/file';

// Resume Update URL

export const resumeUpdateUrl = (profileId: string) => {
  return `https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/${profileId}/advResume`;
};

// Resume headline update URL
export const resumeHeadlineUrl =
  'https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/fullprofiles';
