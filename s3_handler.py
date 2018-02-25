from __future__ import print_function
from botocore.exceptions import ClientError
import ast
import boto3
import logging
import os
import sys
import traceback
import time
# xxxpylint: disable=print-statement

LOG_FILE_NAME = 'output.log'

REGION = 'us-east-2'

class S3Handler:
    """S3 handler."""

    def __init__(self):
        self.client = boto3.client('s3')

        logging.basicConfig(filename=LOG_FILE_NAME,
                            level=logging.DEBUG, filemode='w',
                            format='%(asctime)s %(message)s',
                            datefmt='%m/%d/%Y %I:%M:%S %p')
        self.logger = logging.getLogger("S3Handler")

    def help(self):
        print("Supported Commands:")
        print("1. createdir <bucket_name>")
        print("2. upload <source_file_name> <bucket_name> [<dest_object_name>]")
        print("3. download <dest_object_name> <bucket_name> [<source_file_name>]")
        print("4. delete <dest_object_name> <bucket_name>")
        print("5. deletedir <bucket_name>")
        print("6. find <file_extension> [<bucket_name>] -- e.g.: 1. find txt  2. find txt bucket1 --")
        print("7. listdir [<bucket_name>]")
    
    def _error_messages(self, issue):
        error_message_dict = {}
        error_message_dict['incorrect_parameter_number'] = 'Incorrect number of parameters provided'
        error_message_dict['not_implemented'] = 'Functionality not implemented yet!'
        error_message_dict['bucket_name_exists'] = 'Directory already exists.'
        error_message_dict['bucket_name_empty'] = 'Directory name cannot be empty.'
        error_message_dict['bucket_not_empty'] = 'Directory is not empty. Delete objects before proceeding.'
        error_message_dict['missing_source_file'] = 'Source file cannot be found.'
        error_message_dict['non_existent_bucket'] = 'Directory does not exist.'
        error_message_dict['non_existent_object'] = 'Destination object does not exist.'
        error_message_dict['not_authorized_bucket'] = 'You are not authorized to access this directory'
        error_message_dict['unknown_error'] = 'Something was not correct with the request. Try again.'

        if issue:
            return error_message_dict[issue]
        else:
            return error_message_dict['unknown_error']

    def _get_file_extension(self, file_name):
        if os.path.exists(file_name):
            return os.path.splitext(file_name)

    def _get(self, bucket_name):
        response = ''
        try:
            response = self.client.head_bucket(Bucket=bucket_name)
        except Exception as e:
            # print(e)
            # traceback.print_exc(file=sys.stdout)
            
            response_code = e.response['Error']['Code']
            if response_code == '404':
                return False
            elif response_code == '200':
                return True
            else:
                raise e
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return True
        else:
            return False

    def _get_object(self, bucket_name, object_name):
        response = ''
        try:
            response = self.client.head_object(Bucket=bucket_name, Key=object_name)
        except Exception as e:
            response_code = e.response['Error']['Code']
            if response_code == '404':
                return False
            elif response_code == '200':
                return True
            else:
                raise e
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return True
        else:
            return False

    def createdir(self, bucket_name):
        if not bucket_name:
            return self._error_messages('bucket_name_empty')

        try:
            if self._get(bucket_name):
                return self._error_messages('bucket_name_exists')
            self.client.create_bucket(Bucket=bucket_name,
                                      CreateBucketConfiguration={'LocationConstraint': REGION})
        except Exception as e:
            print(e)
            raise e

        # Success response
        operation_successful = ('Directory %s created.' % bucket_name)
        return operation_successful

    def listdir(self, bucket_name):
        result = []

        # If bucket_name is empty then display the names of all the buckets
        if not bucket_name:
            bucket_list = self.client.list_buckets()
            buckets = bucket_list['Buckets']
            print('Avaliable buckets list:')
            for bucket in buckets:
                result.append(bucket['Name'])

        # If bucket_name is provided, check that bucket exits.
        else:
            if not self._get(bucket_name):
                return self._error_messages('non_existent_bucket')
        # If bucket_name is provided then display the names of all objects in the bucket
            object_list = self.client.list_objects_v2(
                Bucket=bucket_name
            )
            #objects = object_list['Name']
            print('Available objects in directory %s:' % bucket_name)
            for obj in object_list:
                result.append(object_list['Name'])

        return ', '.join(result)

    def upload(self, source_file_name, bucket_name, dest_object_name=''):
        # 1. Parameter Validation
        #    - source_file_name exits in current directory
        #    - bucket_name exists
        if not os.path.exists(source_file_name):
            return self._error_messages('missing_source_file')

        if not self._get(bucket_name):
            return self._error_messages('non_existent_bucket')

        # 2. If dest_object_name is not specified then use the source_file_name as dest_object_name
        if dest_object_name == '':
            dest_object_name = source_file_name

        # 3. SDK call
        #    - When uploading the source_file_name and add it to object's meta-data
        #    - Use self._get_file_extension() method to get the extension of the file.
        file_extension = self._get_file_extension(source_file_name)
        action = self.client.upload_file(source_file_name, bucket_name, dest_object_name, ExtraArgs={'ContentType': file_extension[1]})

        try:
            action
        except Exception as e:
            return ("Failed to upload %s to %s: %s" % (source_file_name, '/'.join([bucket_name, dest_object_name]), e))

        # Success response
        operation_successful = ('File %s uploaded to bucket %s.' % (source_file_name, bucket_name))

        return operation_successful


    def download(self, dest_object_name, bucket_name, source_file_name=''):
        # if source_file_name is not specified then use the dest_object_name as the source_file_name
        # If the current directory already contains a file with source_file_name then move it as a backup
        # with following format: <source_file_name.bak.current_time_stamp_in_millis>
        
        # Parameter Validation
        if not self._get(bucket_name):                          #check for directory
            return self._error_messages('non_existent_bucket')
        if not self._get_object(bucket_name, dest_object_name):      #check for object
            return self._error_messages('non_existent_object')

        if source_file_name == '':
            source_file_name = dest_object_name 

        #create backup file
        if os.path.exists(source_file_name):
            time_in_millis = int(round(time.time() * 1000))
            source_file_name = source_file_name + '.bak.' + str(time_in_millis)
        
        # SDK Call
        action = self.client.download_file(bucket_name, dest_object_name, source_file_name)

        try:
            action
        except Exception as e:
            return ("Failed to download %s to %s: %s" % (dest_object_name, '/'.join([bucket_name, source_file_name]), e))

        # Success response
        operation_successful = ('Object %s downloaded from bucket %s.' % (dest_object_name, bucket_name))

        return operation_successful


    def delete(self, dest_object_name, bucket_name):
        # Parameter Validation
        if not self._get(bucket_name):                              #check for directory
            return self._error_messages('non_existent_bucket')
        if not self._get_object(bucket_name, dest_object_name):     #check for object
            return self._error_messages('non_existent_object')

        action = self.client.delete_object(
            Bucket=bucket_name,
            Key=dest_object_name
        )

        try:
            action
        except Exception as e:
            return ("Failed to delete %s from directory %s: %s" % (dest_object_name, bucket_name, e))
        
        # Success response
        operation_successful = ('Object %s deleted from bucket %s.' % (dest_object_name, bucket_name))
        
        return operation_successful


    def deletedir(self, bucket_name):
        # Parameter Validation
        if not self._get(bucket_name):          #check for directory
            return self._error_messages('non_existent_bucket')

        # Delete the bucket only if it is empty
        try:
            self.client.delete_bucket(
                Bucket=bucket_name
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketNotEmpty':
                return self._error_messages('bucket_not_empty')
            else:
                return ('Failed to delete bucket %s: %s' % (bucket_name, e) )
            return e
        
        # Success response
        operation_successful = ("Deleted bucket %s." % bucket_name)
        
        return operation_successful


    def find(self, file_extension, bucket_name=''):
        # Return object names that match the given file extension

        # If bucket_name is specified then search for objects in that bucket.
        # If bucket_name is empty then search all buckets
        

        
        return self._error_messages('not_implemented')


    def dispatch(self, command_string):
        parts = command_string.split(" ")
        response = ''

        if parts[0] == 'createdir':
            # Figure out bucket_name from command_string
            if len(parts) > 1:
                bucket_name = parts[1]
                response = self.createdir(bucket_name)
            else:
                # Parameter Validation
                # - Bucket name is not empty
                response = self._error_messages('bucket_name_empty')
        elif parts[0] == 'upload':
            # Figure out parameters from command_string
            # source_file_name and bucket_name are compulsory; dest_object_name is optional
            # Use self._error_messages['incorrect_parameter_number'] if number of parameters is less
            # than number of compulsory parameters
            if len(parts) < 3:
                return self._error_messages('incorrect_parameter_number')
            source_file_name = parts[1]
            bucket_name = parts[2]
            dest_object_name = ''
            if len(parts) > 3:
                dest_object_name = parts[3]
            response = self.upload(source_file_name, bucket_name, dest_object_name)
        elif parts[0] == 'download':
            # Figure out parameters from command_string
            # dest_object_name and bucket_name are compulsory; source_file_name is optional
            # Use self._error_messages['incorrect_parameter_number'] if number of parameters is less
            # than number of compulsory parameters
            if len(parts) < 3:
                return self._error_messages('incorrect_parameter_number')
            dest_object_name = parts[1]
            bucket_name = parts[2]
            source_file_name = ''
            if len(parts) > 3:
                source_file_name = parts[3]
            response = self.download(dest_object_name, bucket_name, source_file_name)
        elif parts[0] == 'delete':
            if len(parts) < 3:
                return self._error_messages('incorrect_parameter_number')
            dest_object_name = parts[1]
            bucket_name = parts[2]
            response = self.delete(dest_object_name, bucket_name)
        elif parts[0] == 'deletedir':
            if len(parts) < 2:
                return self._error_messages('incorrect_parameter_number')
            bucket_name = parts[1]
            response = self.deletedir(bucket_name)
        elif parts[0] == 'find':
            file_extension = ''
            bucket_name = ''
            response = self.find(file_extension, bucket_name)
        elif parts[0] == 'listdir':
            bucket_name = ''
            if len(parts) > 1:
                bucket_name = parts[1]
            response = self.listdir(bucket_name)
        else:
            response = "Command not recognized."
        return response


def main():

    s3_handler = S3Handler()
    
    while True:
        try:
            command_string = ''
            if sys.version_info[0] < 3:
                command_string = raw_input("Enter command ('help' to see all commands, 'exit' to quit)>")
            else:
                command_string = input("Enter command ('help' to see all commands, 'exit' to quit)>")
    
            # Remove multiple whitespaces, if they exist
            command_string = " ".join(command_string.split())
            
            if command_string == 'exit':
                print("Goodbye!")
                exit()
            elif command_string == 'help':
                s3_handler.help()
            else:
                response = s3_handler.dispatch(command_string)
                print(response)
        except Exception as e:
            print(e)

if __name__ == '__main__':
    main()