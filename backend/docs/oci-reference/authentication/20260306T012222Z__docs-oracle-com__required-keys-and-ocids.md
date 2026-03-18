---
title: "Required Keys and OCIDs"
source: "https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm"
fetched: "20260306T012222Z"
---

You can use the Console to generate the private/public key pair for you. If you already have a key pair, you can choose to upload the public key. When you use the Console to add the key pair, the Console also generates a configuration file preview snippet for you.

The following procedures work for a regular user or an administrator. Administrators can manage API keys for either another user or themselves.

**About the Config File Snippet**

When you use the Console to add the API signing key pair, a configuration file preview snippet is generated with the following information:

  - `user` - the OCID of the user for whom the key pair is being added.
  - `fingerprint` - the fingerprint of the key that was just added.
  - `tenancy` - your tenancy's OCID.
  - `region` - the currently selected region in the Console.
  - `key_file`- the path to your downloaded private key file. You must update this value to the path on your file system where you saved the private key file.

If your config file already has a DEFAULT profile, you'll need to do one of the following:

  - Replace the existing profile and its contents.
  - Rename the existing profile.
  - Rename this profile to a different name after pasting it into the config file.

You can copy this snippet into your config file, to help you get started. If you don't already have a config file, see SDK and CLI Configuration File for details on how to create one. You can also retrieve the config file snippet later for an API signing key whenever you need it. See: To get the config file snippet for an API signing key.

#### To generate an API signing key pair

**Prerequisite:** Before you generate a key pair, create the `.oci` directory in your home directory to store the credentials. See SDK and CLI Configuration File for more details.

1.  View the user's details:
    
      - If you're adding an API key for *yourself*:
        
        In the **navigation menuÂ **, select the **Profile** menu ![Profile menu icon](../../libraries/global-block-libraries/../../Resources/Images/usermenu.png) and then select **User settings**.
        
      - If you're an administrator adding an API key for *another user*: Open the **navigation menuÂ ** and select **Identity & Security**. Under **Identity**, select **Users**. Locate the user in the list, and then click the user's name to view the details.

2.  In the **Resources** section at the bottom left, click **API Keys**

3.  Click **Add API Key** at the top left of the **API Keys** list. The **Add API Key** dialog displays.

4.  Click **Download Private Key** and save the key to your `.oci` directory. In most cases, you do not need to download the public key.
    
    **Note**: If your browser downloads the private key to a different directory, be sure to move it to your `.oci` directory.

5.  Click **Add**.
    
    The key is added and the **Configuration File Preview** is displayed. The file snippet includes required parameters and values you'll need to create your configuration file. Copy and paste the configuration file snippet from the text box into your `~/.oci/config file`. (If you have not yet created this file, see SDK and CLI Configuration File for details on how to create one.)
    
    After you paste the file contents, you'll need to update the `key_file` parameter to the location where you saved your private key file.
    
    
    
    If your config file already has a DEFAULT profile, you'll need to do one of the following:
    
      - Replace the existing profile and its contents.
      - Rename the existing profile.
      - Rename this profile to a different name after pasting it into the config file.
    
    

6.  Update the permissions on your downloaded private key file so that only you can view it:
    
    1.  Go to the `.oci` directory where you placed the private key file.
    2.  Use the command `chmod go-rwx                                         ~/.oci/<oci_api_keyfile>.pem` to set the permissions on the file.

#### To upload or paste an API key

**Prerequisite:** You have generated a public **RSA key in PEM format (minimum 2048 bits)**. The PEM format looks something like this:

    -----BEGIN PUBLIC KEY-----
    MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoTFqF...
    ...
    -----END PUBLIC KEYââ

1.  View the user's details:
    
      - If you're adding an API key for *yourself*:
        
        In the **navigation menuÂ **, select the **Profile** menu ![Profile menu icon](../../libraries/global-block-libraries/../../Resources/Images/usermenu.png) and then select **User settings**.
        
      - If you're an administrator adding an API key for *another user*: Open the **navigation menuÂ ** and select **Identity & Security**. Under **Identity**, select **Users**. Locate the user in the list, and then click the user's name to view the details.

2.  In the **Resources** section at the bottom left, click **API Keys**

3.  Click **Add API Key** at the top left of the **API Keys** list. The **Add API Key** dialog displays.

4.  In the dialog, select **Choose Public Key File** to upload your file, or **Paste Public Key**, if you prefer to paste it into a text box

5.  Click **Add**.
    
    The key is added and the **Configuration File Preview** is displayed. The file snippet includes required parameters and values you'll need to create your configuration file. Copy and paste the configuration file snippet from the text box into your `~/.oci/config file`. (If you have not yet created this file, see SDK and CLI Configuration File for details on how to create one.)
    
    After you paste the file contents, you'll need to update the `key_file` parameter to the location where you saved your private key file.
    
    If your config file already has a DEFAULT profile, you'll need to do one of the following:
    
      - Replace the existing profile and its contents.
      - Rename the existing profile.
      - Rename this profile to a different name after pasting it into the config file.

To get the config file snippet for an API signing key

The following procedure works for a regular user or an administrator.

1.  View the user's details:
    
      - If you're getting an API key config file snippet for *yourself*:
        
        In the **navigation menuÂ **, select the **Profile** menu ![Profile menu icon](../../libraries/global-block-libraries/../../Resources/Images/usermenu.png) and then select **User settings**.
        
      - If you're an administrator getting an API key config file snippet for *another user*: Open the **navigation menuÂ ** and select **Identity & Security**. Under **Identity**, select **Users**. Locate the user in the list, and then click the user's name to view the details.

2.  Under the **Resources** section at the bottom left, click **API Keys**

3.  On the left side of the page, click **API Keys**. The list of API key fingerprints is displayed.

4.  Click the the for the fingerprint, and select **View configuration file**.
    
    The **Configuration File Preview** is displayed. The file snippet includes required parameters and values you'll need to create your configuration file. Copy and paste the configuration file snippet from the text box into your `~/.oci/config file`. (If you have not yet created this file, see SDK and CLI Configuration File for details on how to create one.) After you paste the file contents, you'll need to update the `key_file` parameter to the location where you saved your private key file.
    
    
    
    If your config file already has a DEFAULT profile, you'll need to do one of the following:
    
      - Replace the existing profile and its contents.
      - Rename the existing profile.
      - Rename this profile to a different name after pasting it into the config file.